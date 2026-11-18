"""
Workspace governance policies: rename rules, content zoning, and extensible settings.
"""

from __future__ import annotations

import fnmatch
import os
from enum import StrEnum
from pathlib import Path

from pydantic import BaseModel, Field

from dartfx.workspace.sniffers.chain import sniff_file
from dartfx.workspace.sniffers.extension import classify_by_extension
from dartfx.workspace.sniffers.magic import sniff_magic_bytes
from dartfx.workspace.sniffers.models import FileFormat, FileType, SnifferResult
from dartfx.workspace.sniffers.text import sniff_text_heuristic
from dartfx.workspace.utils import detect_system_generated


class PolicyViolationError(ValueError):
    """Base exception raised when an operation violates a configured workspace policy."""


class RenamePolicyViolationError(PolicyViolationError):
    """Raised when a file rename or move violates the workspace rename policy."""


class IngestionPolicyViolationError(PolicyViolationError):
    """Raised when file upload, import, or placement violates a workspace zone or ingestion policy."""


class RenameMode(StrEnum):
    """Policy mode controlling file extension/format changes during rename/move."""

    SAME_FORMAT = "same_format"
    SAME_TYPE = "same_type"
    STRICT = "strict"
    PERMISSIVE = "permissive"


class RenamePolicy(BaseModel):
    """Configuration for file rename and move operations."""

    mode: RenameMode = RenameMode.SAME_FORMAT
    allow_sidecar_rename: bool = False
    allow_cross_zone_move: bool = True


class ZoneRule(BaseModel):
    """Content governance rule for a workspace path pattern (e.g. 'data/**', 'docs/**')."""

    pattern: str
    allowed_types: list[str] = Field(default_factory=list)
    disallowed_types: list[str] = Field(default_factory=list)
    allowed_formats: list[str] = Field(default_factory=list)
    disallowed_formats: list[str] = Field(default_factory=list)
    allowed_extensions: list[str] = Field(default_factory=list)
    disallowed_extensions: list[str] = Field(default_factory=list)
    max_size_bytes: int | None = None
    allow_unrecognized: bool = True
    allow_system_generated: bool = True


def default_zone_rules() -> list[ZoneRule]:
    """Return canonical content zoning rules for standard workspace directories."""
    return [
        ZoneRule(
            pattern="data/**",
            allowed_types=[FileType.DATA.value, FileType.COMPRESSED.value],
            allow_system_generated=True,
        ),
        ZoneRule(
            pattern="docs/**",
            allowed_types=[FileType.DOCUMENTATION.value, FileType.MEDIA.value],
        ),
        ZoneRule(
            pattern="code/**",
            allowed_types=[FileType.CODE.value],
        ),
        ZoneRule(
            pattern="meta/**",
            allowed_types=[FileType.METADATA.value],
        ),
        ZoneRule(
            pattern="work/**",
        ),
    ]


class IngestionPolicy(BaseModel):
    """Configuration for file upload, import, and path-based zone restrictions."""

    enforce_zones: bool = True
    max_upload_size_bytes: int | None = None
    zones: list[ZoneRule] = Field(default_factory=default_zone_rules)


class WorkspaceSettings(BaseModel):
    """Extensible workspace-level configuration and governance policies."""

    version: int = 1
    rename: RenamePolicy = Field(default_factory=RenamePolicy)
    ingestion: IngestionPolicy = Field(default_factory=IngestionPolicy)


def default_workspace_settings() -> WorkspaceSettings:
    """Build default WorkspaceSettings, respecting optional system environment overrides."""
    rename_mode_raw = os.environ.get("DARTFX_RENAME_MODE", "").strip().lower()
    rename_mode = RenameMode.SAME_FORMAT
    if rename_mode_raw:
        try:
            rename_mode = RenameMode(rename_mode_raw)
        except ValueError:
            pass

    enforce_zones_raw = os.environ.get("DARTFX_ENFORCE_ZONES", "").strip().lower()
    enforce_zones = True
    if enforce_zones_raw in {"0", "false", "no", "off"}:
        enforce_zones = False
    elif enforce_zones_raw in {"1", "true", "yes", "on"}:
        enforce_zones = True

    return WorkspaceSettings(
        rename=RenamePolicy(mode=rename_mode),
        ingestion=IngestionPolicy(enforce_zones=enforce_zones),
    )


def _match_zone_pattern(rel_path: str, pattern: str) -> bool:
    """Match a normalized workspace-relative POSIX path against a zone pattern."""
    clean_rel = rel_path.lstrip("/")
    clean_pat = pattern.lstrip("/")
    if clean_pat.endswith("/**"):
        prefix = clean_pat[:-3].rstrip("/")
        return clean_rel == prefix or clean_rel.startswith(prefix + "/")
    return fnmatch.fnmatch(clean_rel, clean_pat)


def _classify_intended_file(filename_or_path: Path, content_path: Path | None = None) -> SnifferResult:
    """Classify an intended destination file using its filename and optional staged content."""
    result = classify_by_extension(filename_or_path)
    if result is None and content_path is not None and content_path.exists():
        result = sniff_magic_bytes(content_path) or sniff_text_heuristic(content_path)
    if result is None:
        return SnifferResult(
            file_type=FileType.OTHER,
            file_format=FileFormat.UNDETERMINED,
            confidence=0.1,
        )
    return result


class PolicyEvaluator:
    """Evaluates workspace rename and ingestion/zone policies."""

    @staticmethod
    def find_matching_zone(rel_path: str, rules: list[ZoneRule]) -> ZoneRule | None:
        """Return the first ZoneRule matching the workspace-relative path, if any."""
        for rule in rules:
            if _match_zone_pattern(rel_path, rule.pattern):
                return rule
        return None

    @classmethod
    def evaluate_rename(
        cls,
        settings: WorkspaceSettings,
        src: Path,
        dst: Path,
        *,
        workspace_root: Path | None = None,
        allow_override: bool = False,
    ) -> None:
        """Validate a file rename/move against the workspace RenamePolicy and target ZoneRule."""
        if allow_override or not src.is_file():
            return

        policy = settings.rename

        # 1. Direct sidecar rename check
        is_gen, _ = detect_system_generated(src)
        if is_gen and not policy.allow_sidecar_rename:
            raise RenamePolicyViolationError(
                f"Direct rename of system-generated artifact '{src.name}' is disallowed by workspace policy. "
                "Rename the parent dataset instead."
            )

        # 2. Extension / format preservation check
        src_ext = src.suffix.lower()
        dst_ext = dst.suffix.lower()

        if policy.mode != RenameMode.PERMISSIVE and src_ext != dst_ext:
            if policy.mode == RenameMode.STRICT:
                raise RenamePolicyViolationError(
                    f"Workspace rename policy 'strict' prevents changing file extension "
                    f"from '{src_ext or '(none)'}' to '{dst_ext or '(none)'}'."
                )

            src_info = sniff_file(src)
            dst_info = classify_by_extension(dst)

            if policy.mode == RenameMode.SAME_FORMAT:
                if dst_info is None or dst_info.file_format != src_info.file_format:
                    dst_fmt = dst_info.file_format.value if dst_info else "undetermined"
                    raise RenamePolicyViolationError(
                        f"Workspace rename policy 'same_format' prevents changing format from "
                        f"'{src_info.file_format.value}' ('{src_ext or '(none)'}') to "
                        f"'{dst_fmt}' ('{dst_ext or '(none)'}')."
                    )
            elif policy.mode == RenameMode.SAME_TYPE:
                if dst_info is None or dst_info.file_type != src_info.file_type:
                    dst_type = dst_info.file_type.value if dst_info else "undetermined"
                    raise RenamePolicyViolationError(
                        f"Workspace rename policy 'same_type' prevents changing file type from "
                        f"'{src_info.file_type.value}' to '{dst_type}'."
                    )

        # 3. Target zone check when moving across directories
        if settings.ingestion.enforce_zones and workspace_root is not None:
            try:
                dst_rel = dst.relative_to(workspace_root).as_posix()
            except ValueError:
                return
            try:
                src_rel = src.relative_to(workspace_root).as_posix()
            except ValueError:
                src_rel = ""

            if not policy.allow_cross_zone_move:
                src_zone = cls.find_matching_zone(src_rel, settings.ingestion.zones)
                dst_zone = cls.find_matching_zone(dst_rel, settings.ingestion.zones)
                if src_zone != dst_zone:
                    raise RenamePolicyViolationError(
                        f"Cross-zone moves are disallowed by workspace policy ('{src_rel}' -> '{dst_rel}')."
                    )

            cls.evaluate_ingestion(
                settings,
                dst,
                dst_rel,
                content_path=src,
                size_bytes=src.stat().st_size,
                is_generated=is_gen,
                allow_override=False,
            )

    @classmethod
    def evaluate_ingestion(
        cls,
        settings: WorkspaceSettings,
        filename_or_path: Path | str,
        dest_rel_path: str,
        *,
        content_path: Path | None = None,
        size_bytes: int | None = None,
        is_generated: bool | None = None,
        allow_override: bool = False,
    ) -> None:
        """Validate a file upload/placement against IngestionPolicy and matching ZoneRule."""
        if allow_override:
            return

        policy = settings.ingestion

        if (
            policy.max_upload_size_bytes is not None
            and size_bytes is not None
            and size_bytes > policy.max_upload_size_bytes
        ):
            raise IngestionPolicyViolationError(
                f"File '{dest_rel_path}' ({size_bytes} bytes) exceeds workspace maximum upload size "
                f"({policy.max_upload_size_bytes} bytes)."
            )

        if not policy.enforce_zones or not policy.zones:
            return

        zone = cls.find_matching_zone(dest_rel_path, policy.zones)
        if zone is None:
            return

        target_p = Path(filename_or_path)
        if is_generated is None:
            is_generated, _ = detect_system_generated(target_p)

        # System-generated sidecars are permitted in zones with allow_system_generated=True
        if is_generated and zone.allow_system_generated:
            return

        if zone.max_size_bytes is not None and size_bytes is not None and size_bytes > zone.max_size_bytes:
            raise IngestionPolicyViolationError(
                f"File '{dest_rel_path}' ({size_bytes} bytes) exceeds maximum size ({zone.max_size_bytes} bytes) "
                f"for zone '{zone.pattern}'."
            )

        ext = target_p.suffix.lower()
        if zone.allowed_extensions:
            allowed_exts = {e.lower() if e.startswith(".") else f".{e.lower()}" for e in zone.allowed_extensions}
            if ext not in allowed_exts:
                raise IngestionPolicyViolationError(
                    f"Extension '{ext or '(none)'}' is not permitted in zone '{zone.pattern}'. "
                    f"Allowed extensions: {sorted(allowed_exts)}."
                )

        if zone.disallowed_extensions:
            disallowed_exts = {e.lower() if e.startswith(".") else f".{e.lower()}" for e in zone.disallowed_extensions}
            if ext in disallowed_exts:
                raise IngestionPolicyViolationError(
                    f"Extension '{ext}' is explicitly disallowed in zone '{zone.pattern}'."
                )

        info = _classify_intended_file(target_p, content_path=content_path)

        if not zone.allow_unrecognized and info.file_format == FileFormat.UNDETERMINED:
            raise IngestionPolicyViolationError(
                f"Unrecognized file format for '{target_p.name}' is not permitted in zone '{zone.pattern}'."
            )

        if zone.allowed_types:
            allowed_types = {t.lower() for t in zone.allowed_types}
            if info.file_type.value.lower() not in allowed_types:
                raise IngestionPolicyViolationError(
                    f"Cannot place '{target_p.name}' (type: '{info.file_type.value}') in '{zone.pattern}'. "
                    f"Allowed types: {sorted(allowed_types)}."
                )

        if zone.disallowed_types:
            disallowed_types = {t.lower() for t in zone.disallowed_types}
            if info.file_type.value.lower() in disallowed_types:
                raise IngestionPolicyViolationError(
                    f"File type '{info.file_type.value}' is disallowed in zone '{zone.pattern}'."
                )

        if zone.allowed_formats:
            allowed_fmts = {f.lower() for f in zone.allowed_formats}
            if info.file_format.value.lower() not in allowed_fmts:
                raise IngestionPolicyViolationError(
                    f"Format '{info.file_format.value}' is not permitted in zone '{zone.pattern}'. "
                    f"Allowed formats: {sorted(allowed_fmts)}."
                )

        if zone.disallowed_formats:
            disallowed_fmts = {f.lower() for f in zone.disallowed_formats}
            if info.file_format.value.lower() in disallowed_fmts:
                raise IngestionPolicyViolationError(
                    f"Format '{info.file_format.value}' is disallowed in zone '{zone.pattern}'."
                )
