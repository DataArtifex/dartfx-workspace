"""
Step 2: Magic byte sniffer.

Reads the first 32 bytes of a file to identify binary format signatures.
Only invoked when the extension classifier returns ambiguous/undetermined.
"""

import zipfile
from pathlib import Path

from dartfx.workspace.sniffers.models import FileFormat, FileType, SnifferResult

# Magic byte signatures: (offset, bytes, FileType, FileFormat)
MAGIC_SIGNATURES: list[tuple[int, bytes, FileType, FileFormat]] = [
    # Parquet: starts and ends with PAR1
    (0, b"PAR1", FileType.DATA, FileFormat.PARQUET),
    # SPSS .sav: starts with $FL2 or $FL3
    (0, b"$FL2", FileType.DATA, FileFormat.SAV),
    (0, b"$FL3", FileType.DATA, FileFormat.SAV),
    # PDF
    (0, b"%PDF", FileType.DOCUMENTATION, FileFormat.PDF),
]

# SAS7BDAT has a longer, more complex header signature
SAS_MAGIC = b"\x00\x00\x00\x00\x00\x00\x00\x00"
SAS_MAGIC_OFFSET = 0
SAS_HEADER_TEXT = b"SAS FILE"

# Stata .dta files: first byte is a version identifier (0x71=Stata 13, 0x72=Stata 14, etc.)
# followed by specific patterns. We check for the <stata_dta> XML tag in newer versions.
STATA_XML_TAG = b"<stata_dta>"

# ZIP-based formats (xlsx, docx, pptx)
ZIP_MAGIC = b"PK\x03\x04"


def sniff_magic_bytes(file_path: Path) -> SnifferResult | None:
    """Identify a file by its binary header signature.

    Returns None if no known signature matches.
    """
    try:
        with open(file_path, "rb") as f:
            header = f.read(64)
    except OSError:
        return None

    if len(header) < 4:
        return None

    # Check simple magic signatures
    for offset, magic, file_type, file_format in MAGIC_SIGNATURES:
        end = offset + len(magic)
        if len(header) >= end and header[offset:end] == magic:
            return SnifferResult(
                file_type=file_type,
                file_format=file_format,
                confidence=0.95,
            )

    # SAS7BDAT: look for "SAS FILE" marker in the header
    if SAS_HEADER_TEXT in header:
        return SnifferResult(
            file_type=FileType.DATA,
            file_format=FileFormat.SAS7BDAT,
            confidence=0.95,
        )

    # Stata .dta: newer formats contain <stata_dta> XML tag
    if STATA_XML_TAG in header:
        return SnifferResult(
            file_type=FileType.DATA,
            file_format=FileFormat.DTA,
            confidence=0.95,
        )

    # ZIP-based formats: probe the archive to distinguish xlsx/docx/pptx
    if header[:4] == ZIP_MAGIC:
        return _probe_zip(file_path)

    return None


def _probe_zip(file_path: Path) -> SnifferResult | None:
    """Distinguish between xlsx, docx, pptx, and generic zip files."""
    try:
        with zipfile.ZipFile(file_path, "r") as zf:
            names = zf.namelist()
            if any("xl/" in n for n in names):
                return SnifferResult(
                    file_type=FileType.DATA,
                    file_format=FileFormat.XLSX,
                    confidence=0.95,
                )
            if any("word/" in n for n in names):
                return SnifferResult(
                    file_type=FileType.DOCUMENTATION,
                    file_format=FileFormat.DOCX,
                    confidence=0.95,
                )
            if any("ppt/" in n for n in names):
                return SnifferResult(
                    file_type=FileType.DOCUMENTATION,
                    file_format=FileFormat.PPTX,
                    confidence=0.95,
                )
    except (zipfile.BadZipFile, OSError):
        pass
    return None
