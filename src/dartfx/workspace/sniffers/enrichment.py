"""
Step 4: Attribute enrichment sniffer.

Runs AFTER classification to extract format-specific attributes
(version numbers, dialect details, etc.) for formats that support them.
This step runs even for files classified by extension alone.
"""

import json
import logging
from pathlib import Path

from dartfx.workspace.sniffers.models import FileFormat, SnifferResult

logger = logging.getLogger(__name__)

# Formats that support enrichment
ENRICHABLE_FORMATS: set[FileFormat] = {
    FileFormat.SAS7BDAT,
    FileFormat.SAV,
    FileFormat.DTA,
    FileFormat.CSV,
    FileFormat.TSV,
    FileFormat.JSON,
    FileFormat.PDF,
    FileFormat.XLSX,
    FileFormat.DOCX,
    FileFormat.PPTX,
    FileFormat.ZIP,
    FileFormat.GZIP,
}


def enrich_attributes(file_path: Path, result: SnifferResult) -> SnifferResult:
    """Enrich a SnifferResult with format-specific attributes.

    Modifies and returns the same result object with additional
    attributes populated.
    """
    if result.file_format not in ENRICHABLE_FORMATS:
        return result

    if result.file_format in (FileFormat.SAS7BDAT, FileFormat.SAV, FileFormat.DTA):
        _enrich_proprietary(file_path, result)
    elif result.file_format in (FileFormat.CSV, FileFormat.TSV):
        _enrich_delimited(file_path, result)
    elif result.file_format == FileFormat.JSON:
        _enrich_json(file_path, result)
    elif result.file_format == FileFormat.PDF:
        _enrich_pdf(file_path, result)
    elif result.file_format in (FileFormat.XLSX, FileFormat.DOCX, FileFormat.PPTX):
        _enrich_zip_metadata(file_path, result)
    elif result.file_format == FileFormat.ZIP:
        _enrich_zip_metadata(file_path, result, is_archive=True)
    elif result.file_format == FileFormat.GZIP:
        _enrich_gzip_metadata(file_path, result)

    return result


def _enrich_proprietary(file_path: Path, result: SnifferResult) -> None:
    """Extract version and structural info from SAS/SPSS/Stata files using pyreadstat."""
    try:
        import pyreadstat
    except ImportError:
        logger.debug("pyreadstat not available, skipping proprietary format enrichment")
        return

    reader_map = {
        FileFormat.SAS7BDAT: pyreadstat.read_sas7bdat,
        FileFormat.SAV: pyreadstat.read_sav,
        FileFormat.DTA: pyreadstat.read_dta,
    }

    reader = reader_map.get(result.file_format)
    if not reader:
        return

    try:
        _, meta = reader(str(file_path), metadataonly=True)

        if hasattr(meta, "file_label") and meta.file_label:
            result.attributes["fileLabel"] = str(meta.file_label)
        if hasattr(meta, "number_columns") and meta.number_columns is not None:
            result.attributes["variableCount"] = str(meta.number_columns)
        if hasattr(meta, "number_rows") and meta.number_rows is not None:
            result.attributes["rowCount"] = str(meta.number_rows)
        if hasattr(meta, "file_format_version") and meta.file_format_version:
            result.attributes["fileFormatVersion"] = str(meta.file_format_version)

    except Exception:
        logger.debug(f"pyreadstat enrichment failed for {file_path}", exc_info=True)


def _enrich_delimited(file_path: Path, result: SnifferResult) -> None:
    """Extract delimiter and quote character for CSV/TSV files if not already known."""
    if "textDelimiter" in result.attributes:
        # Already enriched by the text heuristic sniffer
        return

    try:
        import clevercsv
    except ImportError:
        logger.debug("clevercsv not available, skipping delimited enrichment")
        return

    try:
        with open(file_path, encoding="utf-8", errors="replace") as f:
            sample = f.read(10_000)

        dialect = clevercsv.Sniffer().sniff(sample, verbose=False)
        if dialect and dialect.delimiter:
            delimiter = dialect.delimiter
            quotechar = dialect.quotechar

            if not delimiter:
                return
            result.attributes["textDelimiter"] = delimiter
            if quotechar:
                result.attributes["textQuote"] = quotechar
    except Exception:
        logger.debug(f"clevercsv enrichment failed for {file_path}", exc_info=True)


def _enrich_json(file_path: Path, result: SnifferResult) -> None:
    """Check if a JSON file contains @context (JSON-LD) and reclassify if so."""
    try:
        with open(file_path, encoding="utf-8", errors="replace") as f:
            # Read only the first 8KB to avoid loading huge JSON files
            sample = f.read(8192)

        data = json.loads(sample)
        if isinstance(data, dict) and "@context" in data:
            result.file_format = FileFormat.JSONLD
            result.mime_type = "application/ld+json"
            result.confidence = 0.95
    except (json.JSONDecodeError, OSError):
        # loading huge JSON files, or simply unreadable, leave as-is.
        pass


def _enrich_pdf(file_path: Path, result: SnifferResult) -> None:
    """Extract version number from PDF header."""
    try:
        with open(file_path, "rb") as f:
            header = f.read(15).decode("ascii", errors="ignore")
            if header.startswith("%PDF-"):
                # Header format is %PDF-1.x
                version = header[5:8].strip()
                result.attributes["fileFormatVersion"] = version
    except Exception:
        pass


def _enrich_zip_metadata(file_path: Path, result: SnifferResult, is_archive: bool = False) -> None:
    """Extract basic properties from ZIP-based formats.

    If is_archive=True, also counts files in the zip and extracts comments.
    """
    import re
    import zipfile

    try:
        with zipfile.ZipFile(file_path, "r") as zf:
            if is_archive:
                result.attributes["itemCount"] = str(len(zf.namelist()))
                if zf.comment:
                    result.attributes["fileLabel"] = zf.comment.decode("utf-8", errors="ignore")

            # For Office formats, check app.xml for core stats
            if "docProps/app.xml" in zf.namelist():
                with zf.open("docProps/app.xml") as f:
                    content = f.read().decode("utf-8", errors="ignore")

                    if result.file_format == FileFormat.XLSX:
                        # Extract sheet count
                        sheets = re.search(r"<Sheets>(\d+)</Sheets>", content)
                        if sheets:
                            result.attributes["sheetCount"] = sheets.group(1)

                    elif result.file_format == FileFormat.DOCX:
                        words = re.search(r"<Words>(\d+)</Words>", content)
                        pages = re.search(r"<Pages>(\d+)</Pages>", content)
                        if words:
                            result.attributes["wordCount"] = words.group(1)
                        if pages:
                            result.attributes["pageCount"] = pages.group(1)

                    elif result.file_format == FileFormat.PPTX:
                        slides = re.search(r"<Slides>(\d+)</Slides>", content)
                        if slides:
                            result.attributes["slideCount"] = slides.group(1)
    except Exception:
        pass


def _enrich_gzip_metadata(file_path: Path, result: SnifferResult) -> None:
    """Extract basic GZIP metadata."""
    try:
        with open(file_path, "rb") as f:
            header = f.read(10)
            if len(header) >= 3 and header[0:2] == b"\x1f\x8b":
                # Third byte is compression method (8 = deflate)
                if header[2] == 8:
                    result.attributes["compressionMethod"] = "deflate"
    except Exception:
        pass
