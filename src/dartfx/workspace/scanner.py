"""
Workspace scanning and file profiling using BLAKE3 hashes.
"""

import uuid
from collections.abc import Callable, Sequence
from datetime import datetime
from pathlib import Path
from uuid import UUID

import blake3

from dartfx.workspace.kb import KnowledgeBase
from dartfx.workspace.sniffers import sniff_file
from dartfx.workspace.utils import detect_system_generated


class Scanner:
    """
    Traverses the workspace, computes BLAKE3 hashes, extracts metadata,
    and classifies files using the sniffer pipeline.
    """

    def __init__(self, workspace_path: Path, kb: KnowledgeBase):
        self.workspace_path = workspace_path
        self.kb = kb
        self.ignore_dirs = {".dartfx", ".git", "__pycache__", "venv", ".venv"}

    def compute_blake3(self, file_path: Path) -> str:
        hasher = blake3.blake3()
        with open(file_path, "rb") as f:
            for chunk in iter(lambda: f.read(65536), b""):
                hasher.update(chunk)
        return hasher.hexdigest()

    def _sniff(self, file_path: Path) -> tuple[str, str, str | None, dict[str, str]]:
        """Run the sniffer pipeline and return (type, format, mime, attributes)."""
        result = sniff_file(file_path)
        return (
            result.file_type.value,
            result.file_format.value,
            result.mime_type,
            result.attributes,
        )

    def scan(
        self,
        target_path: Path | None = None,
        status_callback: Callable[[str], None] | None = None,
    ):
        """
        Scans a portion of the workspace (defaults to root) and synchronizes
        with the Knowledge Base.
        """
        search_root = target_path or self.workspace_path

        existing_files = self.kb.get_all_files()
        existing_path_map = {f["path"]: f for f in existing_files}
        existing_hash_map = {f["blake3_hash"]: f for f in existing_files}

        current_paths = set()

        for p in search_root.rglob("*"):
            if not p.is_file():
                continue

            # Skip ignored directories or hidden files/dirs
            rel_parts = p.relative_to(self.workspace_path).parts
            if any(part.startswith(".") or part in self.ignore_dirs for part in rel_parts):
                continue

            rel_path_str = p.relative_to(self.workspace_path).as_posix()
            current_paths.add(rel_path_str)

            if status_callback:
                status_callback(rel_path_str)

            try:
                stat = p.stat()
                size = stat.st_size
                created = datetime.fromtimestamp(stat.st_ctime)
                updated = datetime.fromtimestamp(stat.st_mtime)
                b3hash = self.compute_blake3(p)
            except Exception as e:
                # Handle unexpected file reading errors gracefully
                print(f"Skipping {p}: {e}")
                continue

            file_type, file_format, mime_type, attributes = self._sniff(p)
            is_gen, gen_by = detect_system_generated(p)

            if rel_path_str in existing_path_map:
                old_f = existing_path_map[rel_path_str]
                if old_f.get("is_generated"):
                    is_gen = True
                    gen_by = old_f.get("generated_by") or gen_by
                source_uuid = old_f.get("source_uuid")
                if old_f["blake3_hash"] != b3hash or old_f["size_bytes"] != size or old_f.get("is_generated") != is_gen:
                    self.kb.upsert_file_resource(
                        uuid.UUID(old_f["uuid"]),
                        p.relative_to(self.workspace_path),
                        size,
                        b3hash,
                        file_type,
                        created,
                        updated,
                        file_format=file_format,
                        mime_type=mime_type,
                        attributes=attributes,
                        is_generated=is_gen,
                        generated_by=gen_by,
                        source_uuid=source_uuid,
                    )
            else:
                # Path not tracked, check if renamed
                uuid_to_use = uuid.uuid4()
                source_uuid = None
                if b3hash in existing_hash_map:
                    suspected_old_file = existing_hash_map[b3hash]
                    old_path_p = self.workspace_path / suspected_old_file["path"]
                    if not old_path_p.exists():
                        # It's a rename! Recover the UUID
                        uuid_to_use = uuid.UUID(suspected_old_file["uuid"])
                        if suspected_old_file.get("is_generated"):
                            is_gen = True
                            gen_by = suspected_old_file.get("generated_by") or gen_by
                        source_uuid = suspected_old_file.get("source_uuid")
                        del existing_hash_map[b3hash]

                self.kb.upsert_file_resource(
                    uuid_to_use,
                    p.relative_to(self.workspace_path),
                    size,
                    b3hash,
                    file_type,
                    created,
                    updated,
                    file_format=file_format,
                    mime_type=mime_type,
                    attributes=attributes,
                    is_generated=is_gen,
                    generated_by=gen_by,
                    source_uuid=source_uuid,
                )

        self.kb.save()

        # Phase 2: Cleanup missing files ONLY within the search root
        updated_kb_files = self.kb.get_all_files()

        # Calculate target relative path for scoped cleanup
        target_rel = search_root.relative_to(self.workspace_path).as_posix()
        if target_rel == ".":
            target_rel = ""

        for f in updated_kb_files:
            f_path = f["path"]
            # Check if file is missing on disk AND it belongs to the scanned target area
            in_target_area = f_path == target_rel or f_path.startswith(target_rel + "/") or target_rel == ""

            if f_path not in current_paths and in_target_area:
                self.kb.remove_file_resource(uuid.UUID(f["uuid"]))

        self.kb.save()

    def scan_path(
        self,
        path: Path,
        *,
        is_generated: bool | None = None,
        generated_by: str | None = None,
        source_uuid: UUID | str | None = None,
    ):
        """Perform targeted profiling and indexing for a single path (file or directory)."""
        if not path.exists():
            return

        if path.is_file():
            self._scan_single_file(
                path,
                is_generated=is_generated,
                generated_by=generated_by,
                source_uuid=source_uuid,
            )
        else:
            for p in path.rglob("*"):
                if p.is_file():
                    self._scan_single_file(
                        p,
                        is_generated=is_generated,
                        generated_by=generated_by,
                        source_uuid=source_uuid,
                    )

    def _scan_single_file(
        self,
        p: Path,
        *,
        is_generated: bool | None = None,
        generated_by: str | None = None,
        source_uuid: UUID | str | None = None,
    ):
        """Helper to scan just one file and update KB."""
        rel_parts = p.relative_to(self.workspace_path).parts
        if any(part.startswith(".") or part in self.ignore_dirs for part in rel_parts):
            return

        rel_path_str = p.relative_to(self.workspace_path).as_posix()
        try:
            stat = p.stat()
            size = stat.st_size
            created = datetime.fromtimestamp(stat.st_ctime)
            updated = datetime.fromtimestamp(stat.st_mtime)
            b3hash = self.compute_blake3(p)
        except Exception as e:
            print(f"Skipping targeted scan of {p}: {e}")
            return

        file_type, file_format, mime_type, attributes = self._sniff(p)
        existing_info = self.kb.get_file_by_path(rel_path_str)

        # Resolve is_generated and generated_by
        resolved_gen = is_generated
        resolved_by = generated_by
        resolved_source_uuid = source_uuid
        if resolved_gen is None:
            if existing_info and existing_info.get("is_generated"):
                resolved_gen = True
                resolved_by = existing_info.get("generated_by") or resolved_by
            else:
                detected_gen, detected_by = detect_system_generated(p)
                resolved_gen = detected_gen
                resolved_by = detected_by or resolved_by

        if resolved_source_uuid is None and existing_info:
            resolved_source_uuid = existing_info.get("source_uuid")

        if existing_info:
            if (
                existing_info["blake3_hash"] != b3hash
                or existing_info["size_bytes"] != size
                or existing_info.get("is_generated") != resolved_gen
                or existing_info.get("source_uuid") != (str(resolved_source_uuid) if resolved_source_uuid else None)
            ):
                self.kb.upsert_file_resource(
                    uuid.UUID(existing_info["uuid"]),
                    p.relative_to(self.workspace_path),
                    size,
                    b3hash,
                    file_type,
                    created,
                    updated,
                    file_format=file_format,
                    mime_type=mime_type,
                    attributes=attributes,
                    is_generated=bool(resolved_gen),
                    generated_by=resolved_by,
                    source_uuid=resolved_source_uuid,
                )
        else:
            self.kb.upsert_file_resource(
                uuid.uuid4(),
                p.relative_to(self.workspace_path),
                size,
                b3hash,
                file_type,
                created,
                updated,
                file_format=file_format,
                mime_type=mime_type,
                attributes=attributes,
                is_generated=bool(resolved_gen),
                generated_by=resolved_by,
                source_uuid=resolved_source_uuid,
            )

    def handle_moves(self, moves: Sequence[tuple[Path, Path]]):
        """Optimized targeted metadata update for multiple moved/renamed files or directories."""
        if not moves:
            return

        resolved_moves: list[tuple[str, str]] = []
        for src, dst in moves:
            try:
                resolved_moves.append(
                    (
                        src.relative_to(self.workspace_path).as_posix(),
                        dst.relative_to(self.workspace_path).as_posix(),
                    )
                )
            except ValueError:
                pass

        if not resolved_moves:
            return

        all_files = self.kb.get_all_files()
        for f in all_files:
            f_path = f["path"]
            for src_rel, dst_rel in resolved_moves:
                if f_path == src_rel or f_path.startswith(src_rel + "/"):
                    try:
                        rel_to_src = Path(f_path).relative_to(src_rel)
                        new_rel = (Path(dst_rel) / rel_to_src).as_posix()
                    except ValueError:
                        continue

                    new_path_obj = self.workspace_path / new_rel
                    if not new_path_obj.exists():
                        continue

                    file_type, file_format, mime_type, attributes = self._sniff(new_path_obj)
                    try:
                        stat = new_path_obj.stat()
                        created = datetime.fromtimestamp(stat.st_ctime)
                        updated = datetime.fromtimestamp(stat.st_mtime)
                    except OSError:
                        continue

                    self.kb.upsert_file_resource(
                        uuid.UUID(f["uuid"]),
                        new_path_obj.relative_to(self.workspace_path),
                        f["size_bytes"],
                        f["blake3_hash"],
                        file_type,
                        created,
                        updated,
                        file_format=file_format,
                        mime_type=mime_type,
                        attributes=attributes,
                        is_generated=f.get("is_generated", False),
                        generated_by=f.get("generated_by"),
                        source_uuid=f.get("source_uuid"),
                    )
                    break

        # Crucial: Save the graph after mass-moving resources
        self.kb.save()

    def handle_move(self, src: Path, actual_dst: Path):
        """Optimized targeted metadata update for moved/renamed files or directories."""
        self.handle_moves([(src, actual_dst)])

    def handle_remove(self, target: Path | Sequence[Path]):
        """Targeted removal of file or directory records from KB."""
        targets: list[Path] = [target] if isinstance(target, Path) else list(target)
        target_rels: set[str] = set()
        for t in targets:
            try:
                target_rels.add(t.relative_to(self.workspace_path).as_posix())
            except ValueError:
                pass

        if not target_rels:
            return

        all_files = self.kb.get_all_files()

        for f in all_files:
            f_path = f["path"]
            if any(f_path == tr or f_path.startswith(tr + "/") for tr in target_rels):
                self.kb.remove_file_resource(uuid.UUID(f["uuid"]))

        # Crucial: Save the graph after mass-removing resources
        self.kb.save()
