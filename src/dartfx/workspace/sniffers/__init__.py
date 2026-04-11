"""
dartfx file format sniffers.

A self-contained, reusable component for detecting file types, formats,
and format-specific attributes. Designed to be portable to a standalone
package (e.g. dartfx-sniffers) without modification.

Public API:
    sniff_file(path, workspace_path=None) -> SnifferResult
    FileType, FileFormat, SnifferResult, MIME_TYPE_MAP
"""

from dartfx.workspace.sniffers.chain import sniff_file
from dartfx.workspace.sniffers.models import (
    MIME_TYPE_MAP,
    FileFormat,
    FileType,
    SnifferResult,
)

__all__ = [
    "FileFormat",
    "FileType",
    "MIME_TYPE_MAP",
    "SnifferResult",
    "sniff_file",
]
