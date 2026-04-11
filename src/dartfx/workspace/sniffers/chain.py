"""
Sniffer chain orchestrator.

Coordinates the full sniffing pipeline:
  Phase A: Classification (extension → magic bytes → text heuristic)
  Phase B: Attribute enrichment (format-specific metadata extraction)
"""

from pathlib import Path

from dartfx.workspace.sniffers.enrichment import enrich_attributes
from dartfx.workspace.sniffers.extension import classify_by_extension
from dartfx.workspace.sniffers.magic import sniff_magic_bytes
from dartfx.workspace.sniffers.models import (
    MIME_TYPE_MAP,
    FileFormat,
    FileType,
    SnifferResult,
)
from dartfx.workspace.sniffers.text import sniff_text_heuristic


def sniff_file(
    file_path: Path,
    workspace_path: Path | None = None,
) -> SnifferResult:
    """Run the full sniffer pipeline on a file.

    This is the primary public API of the sniffers package.

    Args:
        file_path: Absolute path to the file to sniff.
        workspace_path: Optional workspace root for folder heuristics.

    Returns:
        A SnifferResult with type, format, MIME type, and attributes.
    """
    # ── Phase A: Classification ──

    # Step 1: Extension classifier (zero I/O)
    result = classify_by_extension(file_path, workspace_path)

    # Step 2 & 3: Content-based sniffers for ambiguous/undetermined files
    if result is None or result.file_format == FileFormat.UNDETERMINED:
        # Try magic bytes first (fast — reads 64 bytes)
        magic_result = sniff_magic_bytes(file_path)
        if magic_result:
            # Preserve folder-heuristic type if we had one
            if result and result.file_type != FileType.OTHER:
                magic_result.file_type = result.file_type
            result = magic_result
        else:
            # Try text heuristic (reads first 10KB)
            text_result = sniff_text_heuristic(file_path)
            if text_result:
                if result and result.file_type != FileType.OTHER:
                    text_result.file_type = result.file_type
                result = text_result

    # If still nothing, provide a fallback
    if result is None:
        result = SnifferResult(
            file_type=FileType.OTHER,
            file_format=FileFormat.UNDETERMINED,
            confidence=0.1,
        )

    # ── Phase B: Attribute Enrichment ──
    result = enrich_attributes(file_path, result)

    # Resolve MIME type if not already set
    if result.mime_type is None:
        result.mime_type = MIME_TYPE_MAP.get(result.file_format)

    return result
