"""
Core workspace management module.
"""

import collections
import csv
import fnmatch
import importlib
import mimetypes
import os
import re
import shutil
import sqlite3
import tempfile
import zipfile
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, BinaryIO
from uuid import UUID

from dartfx.workspace.access import AccessPolicy, WorkspacePathTraversalError
from dartfx.workspace.kb import KnowledgeBase
from dartfx.workspace.models import (
    FileEntry,
    FilePreview,
    FileType,
    FileTypeStats,
    ResourceDetail,
    SparqlResult,
    TabularQueryResult,
    TaskEvent,
    TreeNode,
    WorkspaceStats,
)
from dartfx.workspace.policy import (
    PolicyEvaluator,
    WorkspaceSettings,
    default_workspace_settings,
)
from dartfx.workspace.scanner import Scanner
from dartfx.workspace.utils import (
    compute_applicable_actions,
    compute_renamed_artifact_path,
    detect_system_generated,
    get_fairify_status,
    get_related_artifacts,
)

IGNORE_DIRS = {".dartfx", ".git", "__pycache__", "venv", ".venv"}
_SAFE_SQL_START_RE = re.compile(r"^\s*(SELECT|WITH)\b", re.IGNORECASE)
_FORBIDDEN_SQL_RE = re.compile(
    r"\b(INSERT|UPDATE|DELETE|DROP|ALTER|CREATE|REPLACE|TRUNCATE|ATTACH|DETACH|COPY|PRAGMA|EXEC|EXECUTE)\b",
    re.IGNORECASE,
)


def _format_type_label(file_type: str | None, file_format: str | None) -> str:
    ft = file_type or "-"
    ff = file_format or "undetermined"
    return f"{ft}/{ff}" if ff != "undetermined" else ft


def _sanitize_sql_table_name(rel_path: str) -> str:
    stem = Path(rel_path).with_suffix("").as_posix()
    name = re.sub(r"[^a-zA-Z0-9_]", "_", stem).strip("_").lower()
    if not name or name[0].isdigit():
        name = f"t_{name}"
    return name


def _compute_usage_bytes(root: Path) -> int:
    if not root.exists():
        return 0
    total = 0
    for p in root.rglob("*"):
        if not p.is_file():
            continue
        rel_parts = p.relative_to(root).parts
        if any(part.startswith(".") or part in IGNORE_DIRS for part in rel_parts):
            continue
        try:
            total += p.stat().st_size
        except OSError:
            continue
    return total


class Workspace:
    """
    Facade for managing workspace initialization and orchestrating
    scans, programmatic file/resource operations, queries, and Knowledge Base interactions.
    """

    def __init__(self, path: Path | str | None = None):
        self.path = Path(path).resolve() if path is not None else Path(os.getcwd()).resolve()

        # Check environment variable first before falling back to .dartfx as per specs
        env_dir = os.environ.get("DARTFX_WORKSPACE_DIR", ".dartfx")
        self.dartfx_dir = self.path / env_dir

        self._kb: KnowledgeBase | None = None
        self._scanner: Scanner | None = None

    @staticmethod
    def _dartfx_dir_for(path: Path) -> Path:
        env_dir = os.environ.get("DARTFX_WORKSPACE_DIR", ".dartfx")
        return path / env_dir

    @classmethod
    def find_nearest_initialized_path(cls, path: Path) -> Path | None:
        """Returns the closest initialized workspace at or above path."""
        candidate = path.resolve()
        while True:
            if cls._dartfx_dir_for(candidate).is_dir():
                return candidate
            if candidate.parent == candidate:
                return None
            candidate = candidate.parent

    @classmethod
    def find_parent_initialized_path(cls, path: Path) -> Path | None:
        """Returns the nearest initialized parent workspace above path (excluding path)."""
        candidate = path.resolve().parent
        while True:
            if cls._dartfx_dir_for(candidate).is_dir():
                return candidate
            if candidate.parent == candidate:
                return None
            candidate = candidate.parent

    @classmethod
    def init(cls, path: Path | None = None, create_dirs: bool = False) -> "Workspace":
        ws = cls(path)
        ws.dartfx_dir.mkdir(parents=True, exist_ok=True)
        if create_dirs:
            # Create standard folders
            for folder in ["code", "docs", "data", "meta", "work"]:
                (ws.path / folder).mkdir(exist_ok=True)
        return ws

    def is_initialized(self) -> bool:
        return self.dartfx_dir.exists() and self.dartfx_dir.is_dir()

    @property
    def settings_path(self) -> Path:
        """Path to the workspace settings JSON file inside .dartfx."""
        return self.dartfx_dir / "settings.json"

    def get_settings(self) -> WorkspaceSettings:
        """Load workspace settings from .dartfx/settings.json, or return defaults."""
        if self.settings_path.is_file():
            try:
                return WorkspaceSettings.model_validate_json(self.settings_path.read_text(encoding="utf-8"))
            except Exception:
                pass
        return default_workspace_settings()

    def save_settings(self, settings: WorkspaceSettings) -> WorkspaceSettings:
        """Persist workspace settings to .dartfx/settings.json."""
        self.dartfx_dir.mkdir(parents=True, exist_ok=True)
        self.settings_path.write_text(settings.model_dump_json(indent=2), encoding="utf-8")
        return settings

    def update_settings(self, patch: dict[str, Any]) -> WorkspaceSettings:
        """Deep-merge a partial settings dictionary into the workspace settings and save."""
        current = self.get_settings().model_dump()
        for key, value in patch.items():
            if isinstance(value, dict) and isinstance(current.get(key), dict):
                current[key] = {**current[key], **value}
            else:
                current[key] = value
        updated = WorkspaceSettings.model_validate(current)
        return self.save_settings(updated)

    @property
    def kb(self) -> KnowledgeBase:
        if not self.is_initialized():
            raise RuntimeError("Workspace is not initialized. Run `workspace init` first.")
        if not self._kb:
            self._kb = KnowledgeBase(self.path)
        return self._kb

    @property
    def scanner(self) -> Scanner:
        if not self.is_initialized():
            raise RuntimeError("Workspace is not initialized. Run `workspace init` first.")
        if not self._scanner:
            self._scanner = Scanner(self.path, self.kb)
        return self._scanner

    def scan(self):
        """Triggers a filesystem scan and KB synchronization."""
        self.scanner.scan()

    def total_usage_bytes(self) -> int:
        """Compute total non-internal user storage used in bytes."""
        return _compute_usage_bytes(self.path)

    def resolve_safe_path(self, rel_path: str | Path, allow_dartfx: bool = False) -> Path:
        """Resolve a workspace-relative path safely without escaping the workspace root."""
        raw = str(rel_path).strip()
        if raw in ("", ".", "/"):
            return self.path

        # Treat leading "/" as workspace root per workspace virtual path semantics
        cleaned = raw.lstrip("/")
        if not cleaned:
            return self.path

        candidate = (self.path / cleaned).resolve()
        if not candidate.is_relative_to(self.path):
            raise WorkspacePathTraversalError(f"Path '{rel_path}' escapes workspace root.")

        if candidate != self.path and not allow_dartfx:
            rel_parts = candidate.relative_to(self.path).parts
            dartfx_name = self.dartfx_dir.name
            if rel_parts and (rel_parts[0] == dartfx_name or rel_parts[0] == ".dartfx"):
                raise WorkspacePathTraversalError(f"Access to internal '{rel_parts[0]}' directory is restricted.")

        return candidate

    def _kb_files_by_path(self) -> dict[str, dict[str, Any]]:
        if not self.is_initialized():
            return {}
        try:
            return {f["path"]: f for f in self.kb.get_all_files()}
        except Exception:
            return {}

    def _build_file_entry(self, item: Path, kb_files: dict[str, dict[str, Any]]) -> FileEntry:
        is_dir = item.is_dir()
        rel_path = item.relative_to(self.path).as_posix()
        kb_info = None if is_dir else kb_files.get(rel_path)
        st = item.stat()
        modified = datetime.fromtimestamp(st.st_mtime, tz=UTC)

        is_gen = False
        gen_by = None
        if kb_info:
            is_gen = kb_info.get("is_generated", False)
            gen_by = kb_info.get("generated_by")
        if not is_gen and not is_dir:
            is_gen, detected_by = detect_system_generated(item)
            if is_gen and not gen_by:
                gen_by = detected_by

        fairify_stat = get_fairify_status(item, is_generated=is_gen) if not is_dir else None
        actions = compute_applicable_actions(
            item.name,
            is_dir=is_dir,
            is_generated=is_gen,
            file_format=kb_info["file_format"] if kb_info else "undetermined",
            file_type=kb_info["type"] if kb_info else ("dir" if is_dir else "-"),
            full_path=item if not is_dir else None,
        )

        return FileEntry(
            name=item.name,
            path=rel_path,
            is_dir=is_dir,
            size_bytes=0 if is_dir else st.st_size,
            modified_at=modified,
            registered=bool(kb_info),
            uuid=kb_info["uuid"] if kb_info else None,
            file_type=kb_info["type"] if kb_info else ("dir" if is_dir else "-"),
            file_format=kb_info["file_format"] if kb_info else "undetermined",
            mime_type=kb_info.get("mime_type") if kb_info else None,
            is_generated=is_gen,
            generated_by=gen_by,
            source_uuid=kb_info.get("source_uuid") if kb_info else None,
            fairify_status=fairify_stat,
            applicable_actions=actions,
        )

    def list_files(
        self,
        target_path: str = ".",
        *,
        recursive: bool = False,
        show_all: bool = False,
        glob_pattern: str | None = None,
        type_filter: str | None = None,
        format_filter: str | None = None,
        mime_filter: str | None = None,
        registered_only: bool | None = None,
    ) -> list[FileEntry]:
        """List files and directories in the workspace with optional filtering."""
        target = self.resolve_safe_path(target_path)
        if not target.exists():
            raise FileNotFoundError(f"Path not found: {target_path}")

        candidates: list[Path] = []
        if not target.is_dir():
            candidates = [target]
        elif recursive:
            for p in sorted(target.rglob("*")):
                rel_p = p.relative_to(target)
                if not show_all and any(part.startswith(".") for part in rel_p.parts):
                    continue
                if glob_pattern and not fnmatch.fnmatch(p.name, glob_pattern):
                    continue
                candidates.append(p)
        else:
            for p in sorted(target.iterdir(), key=lambda item: (not item.is_dir(), item.name.lower())):
                if not show_all and p.name.startswith("."):
                    continue
                if glob_pattern and not fnmatch.fnmatch(p.name, glob_pattern):
                    continue
                candidates.append(p)

        kb_files = self._kb_files_by_path()
        type_regex = re.compile(type_filter, re.I) if type_filter else None
        format_regex = re.compile(format_filter, re.I) if format_filter else None
        mime_regex = re.compile(mime_filter, re.I) if mime_filter else None

        entries: list[FileEntry] = []
        for item in candidates:
            entry = self._build_file_entry(item, kb_files)
            if registered_only is not None and not entry.is_dir and entry.registered != registered_only:
                continue
            if type_regex:
                if entry.is_dir:
                    continue
                if not type_regex.search(_format_type_label(entry.file_type, entry.file_format)):
                    continue
            if format_regex:
                if entry.is_dir or not format_regex.search(entry.file_format):
                    continue
            if mime_regex:
                if entry.is_dir or not mime_regex.search(entry.mime_type or "-"):
                    continue
            entries.append(entry)

        return entries

    def get_tree(
        self,
        target_path: str = ".",
        *,
        max_level: int | None = None,
        type_filter: str | None = None,
        format_filter: str | None = None,
        mime_filter: str | None = None,
    ) -> TreeNode:
        """Build a recursive directory tree representation of the workspace."""
        target = self.resolve_safe_path(target_path)
        if not target.exists():
            raise FileNotFoundError(f"Path not found: {target_path}")

        kb_files = self._kb_files_by_path()
        type_regex = re.compile(type_filter, re.I) if type_filter else None
        format_regex = re.compile(format_filter, re.I) if format_filter else None
        mime_regex = re.compile(mime_filter, re.I) if mime_filter else None

        def _build_node(node_path: Path, level: int) -> TreeNode:
            rel_str = "/" if node_path == self.path else node_path.relative_to(self.path).as_posix()
            if not node_path.is_dir():
                kb_info = kb_files.get(rel_str)
                is_gen = False
                if kb_info:
                    is_gen = kb_info.get("is_generated", False)
                if not is_gen:
                    is_gen, _ = detect_system_generated(node_path)
                actions = compute_applicable_actions(
                    node_path.name,
                    is_dir=False,
                    is_generated=is_gen,
                    file_format=kb_info["file_format"] if kb_info else "undetermined",
                    file_type=kb_info["type"] if kb_info else "-",
                )
                return TreeNode(
                    name=node_path.name,
                    path=rel_str,
                    is_dir=False,
                    registered=bool(kb_info),
                    uuid=kb_info["uuid"] if kb_info else None,
                    file_type=kb_info["type"] if kb_info else "-",
                    file_format=kb_info["file_format"] if kb_info else "undetermined",
                    is_generated=is_gen,
                    source_uuid=kb_info.get("source_uuid") if kb_info else None,
                    applicable_actions=actions,
                )

            children: list[TreeNode] = []
            if max_level is None or level < max_level:
                for child in sorted(node_path.iterdir(), key=lambda p: (not p.is_dir(), p.name.lower())):
                    if child.name.startswith("."):
                        continue
                    if child.is_dir():
                        children.append(_build_node(child, level + 1))
                    else:
                        child_rel = child.relative_to(self.path).as_posix()
                        kb_info = kb_files.get(child_rel)
                        type_lbl = _format_type_label(
                            kb_info["type"] if kb_info else None,
                            kb_info["file_format"] if kb_info else None,
                        )
                        if type_regex and not type_regex.search(type_lbl):
                            continue
                        if format_regex and not format_regex.search((kb_info or {}).get("file_format", "-")):
                            continue
                        if mime_regex and not mime_regex.search((kb_info or {}).get("mime_type") or "-"):
                            continue
                        children.append(_build_node(child, level + 1))

            dir_actions = compute_applicable_actions(node_path.name, is_dir=True)
            return TreeNode(
                name="/" if node_path == self.path else node_path.name,
                path=rel_str,
                is_dir=True,
                is_generated=False,
                applicable_actions=dir_actions,
                children=children,
            )

        return _build_node(target, 0)

    def preview_file(self, rel_path: str, mode: str = "head", num_lines: int = 10) -> FilePreview:
        """Return head or tail text lines from a workspace file."""
        if mode not in ("head", "tail"):
            raise ValueError("Preview mode must be 'head' or 'tail'.")
        if num_lines < 1:
            raise ValueError("num_lines must be at least 1.")

        p = self.resolve_safe_path(rel_path)
        if not p.exists() or not p.is_file():
            raise FileNotFoundError(f"File not found: {rel_path}")

        lines: list[str] = []
        with open(p, encoding="utf-8", errors="replace") as f:
            if mode == "head":
                for _ in range(num_lines):
                    line = f.readline()
                    if not line:
                        break
                    lines.append(line.rstrip("\r\n"))
            else:
                dq: collections.deque[str] = collections.deque(maxlen=num_lines)
                for line in f:
                    dq.append(line.rstrip("\r\n"))
                lines = list(dq)

        return FilePreview(
            path=p.relative_to(self.path).as_posix(),
            mode=mode,
            lines_requested=num_lines,
            lines=lines,
            total_size_bytes=p.stat().st_size,
        )

    def get_resource_detail(self, identifier: str) -> ResourceDetail:
        """Lookup detailed Knowledge Base metadata by resource UUID or relative path."""
        info: dict[str, Any] | None = None
        try:
            parsed_uuid = UUID(identifier)
            info = self.kb.get_file_by_uuid(parsed_uuid)
        except ValueError:
            p = self.resolve_safe_path(identifier)
            if p != self.path:
                rel_path = p.relative_to(self.path).as_posix()
                info = self.kb.get_file_by_path(rel_path)

        if not info:
            raise KeyError(f"Resource not registered in Knowledge Base: {identifier}")

        is_gen = info.get("is_generated", False)
        gen_by = info.get("generated_by")
        if not is_gen:
            is_gen, detected_by = detect_system_generated(info["path"])
            if is_gen and not gen_by:
                gen_by = detected_by

        full_res_path = self.path / info["path"]
        fairify_stat = get_fairify_status(full_res_path, is_generated=is_gen)
        actions = compute_applicable_actions(
            info["path"],
            is_dir=False,
            is_generated=is_gen,
            file_format=info["file_format"],
            file_type=info["type"],
            full_path=full_res_path,
        )

        attrs = self.kb.get_resource_attributes(UUID(info["uuid"]))
        return ResourceDetail(
            uuid=info["uuid"],
            path=info["path"],
            size_bytes=info["size_bytes"],
            blake3_hash=info["blake3_hash"],
            type=info["type"],
            file_format=info["file_format"],
            mime_type=info.get("mime_type"),
            created_at=info["created_at"],
            updated_at=info["updated_at"],
            is_generated=is_gen,
            generated_by=gen_by,
            source_uuid=info.get("source_uuid"),
            fairify_status=fairify_stat,
            applicable_actions=actions,
            attributes=attrs,
        )

    def update_resource_metadata(
        self,
        uuid_val: UUID | str,
        *,
        file_type: str | None = None,
        file_format: str | None = None,
        attributes: dict[str, str] | None = None,
    ) -> ResourceDetail:
        """Update classification or custom attributes for a registered KB resource."""
        parsed_uuid = uuid_val if isinstance(uuid_val, UUID) else UUID(str(uuid_val))
        info = self.kb.get_file_by_uuid(parsed_uuid)
        if not info:
            raise KeyError(f"Resource not registered in Knowledge Base: {parsed_uuid}")

        merged_attrs = self.kb.get_resource_attributes(parsed_uuid)
        if attributes:
            merged_attrs.update(attributes)

        self.kb.upsert_file_resource(
            uuid=parsed_uuid,
            path=Path(info["path"]),
            size_bytes=info["size_bytes"],
            blake3_hash=info["blake3_hash"],
            file_type=file_type or info["type"],
            created_at=datetime.fromisoformat(info["created_at"]),
            updated_at=datetime.fromisoformat(info["updated_at"]),
            file_format=file_format or info["file_format"],
            mime_type=info.get("mime_type"),
            attributes=merged_attrs,
            is_generated=info.get("is_generated", False),
            generated_by=info.get("generated_by"),
            source_uuid=info.get("source_uuid"),
        )
        return self.get_resource_detail(str(parsed_uuid))

    def export_rdf(self, uuid_val: UUID | str | None = None, rdf_format: str = "turtle") -> str:
        """Serialize RDF metadata for a single resource or the full workspace graph."""
        if uuid_val is not None:
            return self.kb.export_resource_rdf(uuid_val, rdf_format=rdf_format)
        return self.kb.export_workspace_rdf(rdf_format=rdf_format)

    def ingest_file(
        self,
        content: bytes | BinaryIO,
        dest_rel_path: str,
        *,
        overwrite: bool = False,
        auto_scan: bool = True,
        quota_bytes: int | None = None,
        allow_policy_override: bool = False,
    ) -> FileEntry:
        """Safely write uploaded bytes/stream into the workspace with quota, policy, and KB indexing."""
        dest_path = self.resolve_safe_path(dest_rel_path)
        if dest_path == self.path:
            raise ValueError("Destination must be a file path, not the workspace root.")
        if dest_path.exists() and dest_path.is_dir():
            raise IsADirectoryError(f"Destination path is a directory: {dest_rel_path}")
        if dest_path.exists() and not overwrite:
            raise FileExistsError(f"File already exists: {dest_rel_path}")

        existing_size = dest_path.stat().st_size if dest_path.exists() else 0
        current_usage = max(0, self.total_usage_bytes() - existing_size)

        dest_path.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp_name = tempfile.mkstemp(prefix=".upload_", dir=str(dest_path.parent))
        tmp_path = Path(tmp_name)
        written = 0
        try:
            with os.fdopen(fd, "wb") as tmp_file:
                if isinstance(content, (bytes, bytearray)):
                    AccessPolicy.check_quota(current_usage, len(content), quota_bytes)
                    tmp_file.write(content)
                    written = len(content)
                else:
                    while True:
                        chunk = content.read(65536)
                        if not chunk:
                            break
                        written += len(chunk)
                        AccessPolicy.check_quota(current_usage, written, quota_bytes)
                        tmp_file.write(chunk)
            rel_dest = dest_path.relative_to(self.path).as_posix()
            PolicyEvaluator.evaluate_ingestion(
                self.get_settings(),
                dest_path,
                rel_dest,
                content_path=tmp_path,
                size_bytes=written,
                allow_override=allow_policy_override,
            )
            tmp_path.replace(dest_path)
        except Exception:
            if tmp_path.exists():
                tmp_path.unlink(missing_ok=True)
            raise

        if auto_scan and self.is_initialized():
            self.scanner.scan_path(dest_path)

        kb_files = self._kb_files_by_path()
        return self._build_file_entry(dest_path, kb_files)

    def resolve_download_path(self, path_or_uuid: str) -> tuple[Path, str]:
        """Resolve a workspace file by relative path or KB UUID and return (abs_path, mime_type)."""
        mime_type: str | None = None
        target_path: Path | None = None

        if self.is_initialized():
            try:
                parsed_uuid = UUID(path_or_uuid)
                info = self.kb.get_file_by_uuid(parsed_uuid)
                if info:
                    target_path = self.resolve_safe_path(info["path"])
                    mime_type = info.get("mime_type")
            except ValueError:
                pass

        if target_path is None:
            target_path = self.resolve_safe_path(path_or_uuid)
            if self.is_initialized() and target_path != self.path:
                rel_str = target_path.relative_to(self.path).as_posix()
                info = self.kb.get_file_by_path(rel_str)
                if info:
                    mime_type = info.get("mime_type")

        if not target_path.exists() or not target_path.is_file():
            raise FileNotFoundError(f"File not found: {path_or_uuid}")

        if not mime_type:
            guessed, _ = mimetypes.guess_type(str(target_path))
            mime_type = guessed or "application/octet-stream"

        return target_path, mime_type

    def create_archive(
        self,
        rel_path: str = ".",
        *,
        output_zip_path: Path | None = None,
        include_kb: bool = False,
    ) -> Path:
        """Package a workspace file, directory, or full workspace as a ZIP archive."""
        target = self.resolve_safe_path(rel_path)
        if not target.exists():
            raise FileNotFoundError(f"Path not found: {rel_path}")

        if output_zip_path is None:
            fd, tmp_name = tempfile.mkstemp(prefix="dartfx_ws_", suffix=".zip")
            os.close(fd)
            zip_path = Path(tmp_name)
        else:
            zip_path = output_zip_path
            zip_path.parent.mkdir(parents=True, exist_ok=True)

        skip_dirs = set(IGNORE_DIRS)
        if include_kb:
            skip_dirs.discard(".dartfx")
            skip_dirs.discard(self.dartfx_dir.name)

        with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
            if target.is_file():
                arcname = target.relative_to(self.path).as_posix()
                zf.write(target, arcname=arcname)
            else:
                for item in sorted(target.rglob("*")):
                    if not item.is_file():
                        continue
                    rel_parts = item.relative_to(self.path).parts
                    if any(part in skip_dirs for part in rel_parts):
                        continue
                    if not include_kb and any(part.startswith(".") for part in rel_parts):
                        continue
                    zf.write(item, arcname=item.relative_to(self.path).as_posix())

        return zip_path

    def mkdir(self, rel_path: str) -> Path:
        """Create a directory inside the workspace."""
        target = self.resolve_safe_path(rel_path)
        target.mkdir(parents=True, exist_ok=True)
        return target

    def move_path(
        self,
        src_rel: str,
        dst_rel: str,
        *,
        cascade_artifacts: bool = True,
        allow_policy_override: bool = False,
    ) -> Path:
        """Move or rename a file or directory while updating the Knowledge Base.

        If `cascade_artifacts` is True and the source is a user dataset (not system-generated),
        any existing related system-generated artifacts (FAIRify / ReadStat metadata) are also
        renamed and moved to match the new dataset name/location, preserving their persistent UUIDs.
        """
        src = self.resolve_safe_path(src_rel)
        dst = self.resolve_safe_path(dst_rel)
        if src == self.path:
            raise ValueError("Cannot move workspace root.")
        if not src.exists():
            raise FileNotFoundError(f"Source path not found: {src_rel}")

        actual_dst = (dst / src.name) if dst.is_dir() else dst

        PolicyEvaluator.evaluate_rename(
            self.get_settings(),
            src,
            actual_dst,
            workspace_root=self.path,
            allow_override=allow_policy_override,
        )

        actual_dst.parent.mkdir(parents=True, exist_ok=True)

        moves_to_track: list[tuple[Path, Path]] = []

        if src.is_file() and cascade_artifacts:
            is_gen, _ = detect_system_generated(src)
            if not is_gen:
                all_kb_files = self.kb.get_all_files() if self.is_initialized() else None
                artifacts = get_related_artifacts(src, kb_files=all_kb_files, workspace_root=self.path)
                for art in artifacts:
                    if art.exists() and art.is_file() and art != src:
                        new_art_path = compute_renamed_artifact_path(art, src, actual_dst)
                        if new_art_path and new_art_path != art:
                            new_art_path.parent.mkdir(parents=True, exist_ok=True)
                            shutil.move(str(art), str(new_art_path))
                            moves_to_track.append((art, new_art_path))

        shutil.move(str(src), str(actual_dst))
        moves_to_track.append((src, actual_dst))

        if self.is_initialized():
            self.scanner.handle_moves(moves_to_track)
        return actual_dst

    def copy_path(
        self,
        src_rel: str,
        dst_rel: str,
        quota_bytes: int | None = None,
        *,
        allow_policy_override: bool = False,
    ) -> Path:
        """Copy a file or directory inside the workspace with optional quota and policy enforcement."""
        src = self.resolve_safe_path(src_rel)
        dst = self.resolve_safe_path(dst_rel)
        if src == self.path:
            raise ValueError("Cannot copy workspace root into itself.")
        if not src.exists():
            raise FileNotFoundError(f"Source path not found: {src_rel}")

        incoming_size = src.stat().st_size if src.is_file() else _compute_usage_bytes(src)
        AccessPolicy.check_quota(self.total_usage_bytes(), incoming_size, quota_bytes)

        actual_dst = (dst / src.name) if dst.is_dir() else dst
        if src.is_dir():
            shutil.copytree(src, actual_dst, dirs_exist_ok=True)
        else:
            rel_dst = actual_dst.relative_to(self.path).as_posix()
            PolicyEvaluator.evaluate_ingestion(
                self.get_settings(),
                actual_dst,
                rel_dst,
                content_path=src,
                size_bytes=incoming_size,
                allow_override=allow_policy_override,
            )
            actual_dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, actual_dst)

        if self.is_initialized():
            self.scanner.scan_path(actual_dst)
        return actual_dst

    def remove_path(self, rel_path: str, *, delete_artifacts: bool = True) -> list[str]:
        """Remove a file or directory inside the workspace and prune the Knowledge Base.

        If `delete_artifacts` is True and the target is a user-provided file (not system-generated),
        any existing related FAIRification / system-generated artifacts (such as .stats.csv,
        .schema.json, .freqs.csv, .idx, .description.md, .readstat.json) will also be deleted.

        Returns:
            list[str]: The relative paths of all deleted files/directories.
        """
        target = self.resolve_safe_path(rel_path)
        if target == self.path:
            raise ValueError("Cannot remove workspace root.")
        if not target.exists():
            raise FileNotFoundError(f"Path not found: {rel_path}")

        removed_targets: list[Path] = [target]

        if target.is_dir():
            shutil.rmtree(target)
        else:
            if delete_artifacts:
                is_gen, _ = detect_system_generated(target)
                if not is_gen:
                    all_kb_files = self.kb.get_all_files() if self.is_initialized() else None
                    for art in get_related_artifacts(target, kb_files=all_kb_files, workspace_root=self.path):
                        if art.exists() and art.is_file() and art != target:
                            try:
                                art.unlink()
                                removed_targets.append(art)
                            except OSError:
                                pass
            target.unlink()

        if self.is_initialized():
            self.scanner.handle_remove(removed_targets)

        return [t.relative_to(self.path).as_posix() for t in removed_targets]

    def query_sparql(self, query_str: str) -> SparqlResult:
        """Execute a read-only SPARQL query against the workspace Knowledge Base."""
        return self.kb.query_sparql(query_str)

    def query_tabular(self, sql: str, max_rows: int = 500) -> TabularQueryResult:
        """Execute a read-only SQL query against CSV/TSV/Parquet files in the workspace."""
        cleaned = sql.strip().rstrip(";")
        if not cleaned:
            raise ValueError("SQL query must not be empty.")
        if not _SAFE_SQL_START_RE.match(cleaned) or _FORBIDDEN_SQL_RE.search(cleaned):
            raise ValueError("Only read-only SELECT or WITH SQL queries are permitted.")

        # Discover tabular data files
        tabular_files: list[tuple[str, Path]] = []
        used_names: set[str] = set()
        for item in sorted(self.path.rglob("*")):
            if not item.is_file():
                continue
            rel_parts = item.relative_to(self.path).parts
            if any(part.startswith(".") or part in IGNORE_DIRS for part in rel_parts):
                continue
            if item.suffix.lower() not in {".csv", ".tsv", ".parquet", ".pq"}:
                continue
            rel_str = item.relative_to(self.path).as_posix()
            base_name = _sanitize_sql_table_name(Path(rel_str).name)
            full_name = _sanitize_sql_table_name(rel_str)
            if base_name not in used_names:
                tabular_files.append((base_name, item))
                used_names.add(base_name)
            if full_name not in used_names:
                tabular_files.append((full_name, item))
                used_names.add(full_name)

        # Prefer DuckDB if installed, else Polars SQLContext, else stdlib SQLite
        try:
            duckdb = importlib.import_module("duckdb")
            return self._query_with_duckdb(duckdb, tabular_files, cleaned, max_rows)
        except ImportError:
            pass

        try:
            pl = importlib.import_module("polars")
            return self._query_with_polars(pl, tabular_files, cleaned, max_rows)
        except ImportError:
            pass

        return self._query_with_sqlite(tabular_files, cleaned, max_rows)

    @staticmethod
    def _query_with_duckdb(
        duckdb_mod: Any, tabular_files: list[tuple[str, Path]], sql: str, max_rows: int
    ) -> TabularQueryResult:
        conn = duckdb_mod.connect(database=":memory:")
        try:
            for table_name, file_path in tabular_files:
                safe_path = str(file_path).replace("'", "''")
                suffix = file_path.suffix.lower()
                if suffix in (".parquet", ".pq"):
                    stmt = f"CREATE OR REPLACE VIEW \"{table_name}\" AS SELECT * FROM read_parquet('{safe_path}')"
                elif suffix == ".tsv":
                    stmt = (
                        f'CREATE OR REPLACE VIEW "{table_name}" AS '
                        f"SELECT * FROM read_csv_auto('{safe_path}', delim='\\t')"
                    )
                else:
                    stmt = f"CREATE OR REPLACE VIEW \"{table_name}\" AS SELECT * FROM read_csv_auto('{safe_path}')"
                conn.execute(stmt)
            conn.execute("SET enable_external_access=false")
            cursor = conn.execute(sql)
            columns = [desc[0] for desc in (cursor.description or [])]
            fetched = cursor.fetchmany(max_rows)
            rows = [dict(zip(columns, row, strict=False)) for row in fetched]
            return TabularQueryResult(columns=columns, rows=rows, row_count=len(rows))
        finally:
            conn.close()

    @staticmethod
    def _query_with_polars(
        pl_mod: Any, tabular_files: list[tuple[str, Path]], sql: str, max_rows: int
    ) -> TabularQueryResult:
        ctx = pl_mod.SQLContext()
        for table_name, file_path in tabular_files:
            suffix = file_path.suffix.lower()
            if suffix in (".parquet", ".pq"):
                lf = pl_mod.scan_parquet(file_path)
            elif suffix == ".tsv":
                lf = pl_mod.scan_csv(file_path, separator="\t")
            else:
                lf = pl_mod.scan_csv(file_path)
            ctx.register(table_name, lf)
        df = ctx.execute(sql).head(max_rows).collect()
        columns = list(df.columns)
        rows = df.to_dicts()
        return TabularQueryResult(columns=columns, rows=rows, row_count=len(rows))

    @staticmethod
    def _query_with_sqlite(tabular_files: list[tuple[str, Path]], sql: str, max_rows: int) -> TabularQueryResult:
        conn = sqlite3.connect(":memory:")
        try:
            for table_name, file_path in tabular_files:
                suffix = file_path.suffix.lower()
                if suffix not in (".csv", ".tsv"):
                    continue
                delim = "\t" if suffix == ".tsv" else ","
                with open(file_path, encoding="utf-8", errors="replace", newline="") as f:
                    reader = csv.reader(f, delimiter=delim)
                    headers = next(reader, None)
                    if not headers:
                        continue
                    safe_cols = [
                        re.sub(r"[^a-zA-Z0-9_]", "_", h).strip("_") or f"col_{i}" for i, h in enumerate(headers)
                    ]
                    cols_ddl = ", ".join(f'"{c}" TEXT' for c in safe_cols)
                    conn.execute(f'CREATE TABLE "{table_name}" ({cols_ddl})')
                    placeholders = ", ".join("?" for _ in safe_cols)
                    for row in reader:
                        padded = (row + [""] * len(safe_cols))[: len(safe_cols)]
                        conn.execute(f'INSERT INTO "{table_name}" VALUES ({placeholders})', padded)
            cursor = conn.execute(sql)
            columns = [desc[0] for desc in (cursor.description or [])]
            fetched = cursor.fetchmany(max_rows)
            rows = [dict(zip(columns, row, strict=False)) for row in fetched]
            return TabularQueryResult(columns=columns, rows=rows, row_count=len(rows))
        finally:
            conn.close()

    def run_fairify(self, source_rel_path: str, describe: bool = False) -> TaskEvent:
        """Programmatically execute the qsv fairify workflow on a workspace data file."""
        from dartfx.workspace.tasks import run_fairify_task

        return run_fairify_task(
            self,
            task_id="sync-fairify",
            workspace_id="local",
            source_rel_path=source_rel_path,
            describe=describe,
        )

    def run_readstat(
        self,
        source_rel_path: str,
        output_rel_path: str | None = None,
        *,
        extract_metadata: bool = False,
        force: bool = False,
    ) -> TaskEvent:
        """Programmatically execute readstat conversion or metadata extraction."""
        from dartfx.workspace.tasks import run_readstat_task

        return run_readstat_task(
            self,
            task_id="sync-readstat",
            workspace_id="local",
            source_rel_path=source_rel_path,
            output_rel_path=output_rel_path,
            extract_metadata=extract_metadata,
            force=force,
        )

    def run_tocsv(self, source_rel_path: str, *, force: bool = False) -> TaskEvent:
        """Programmatically convert a readstat-supported statistical file to CSV."""
        from dartfx.workspace.tasks import run_tocsv_task

        return run_tocsv_task(
            self,
            task_id="sync-tocsv",
            workspace_id="local",
            source_rel_path=source_rel_path,
            force=force,
        )

    def stats(self) -> WorkspaceStats:
        """Computes stats based on the latest knowledge base data and filesystem probe."""
        # 1. Get registered files from KB
        kb_files = self.kb.get_all_files()
        registered_paths = {f["path"] for f in kb_files}

        # 2. Get all files from filesystem (excluding ignored)
        all_fs_files = []
        for p in self.path.rglob("*"):
            if not p.is_file():
                continue
            rel_parts = p.relative_to(self.path).parts
            if any(part.startswith(".") or part in IGNORE_DIRS for part in rel_parts):
                continue
            all_fs_files.append(p)

        # 3. Calculate metrics
        types_info = {t: FileTypeStats() for t in FileType}
        reg_count = 0
        reg_size = 0
        unreg_count = 0
        unreg_size = 0

        # Aggregate registered
        for f in kb_files:
            type_str = f["type"]
            size = f["size_bytes"]
            reg_count += 1
            reg_size += size
            try:
                type_enum = FileType(type_str)
            except ValueError:
                type_enum = FileType.OTHER

            types_info[type_enum].count += 1
            types_info[type_enum].size_bytes += size

        # Aggregate unregistered
        for p in all_fs_files:
            rel_path = p.relative_to(self.path).as_posix()
            if rel_path not in registered_paths:
                unreg_count += 1
                unreg_size += p.stat().st_size

        return WorkspaceStats(
            total_files=reg_count + unreg_count,
            total_size_bytes=reg_size + unreg_size,
            registered_count=reg_count,
            registered_size_bytes=reg_size,
            unregistered_count=unreg_count,
            unregistered_size_bytes=unreg_size,
            types_info=types_info,
        )
