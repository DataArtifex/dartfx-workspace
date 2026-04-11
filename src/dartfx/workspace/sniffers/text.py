"""
Step 3: Text heuristic sniffer.

Reads the first few lines of a text file to detect delimited tabular data.
Uses clevercsv for high-accuracy CSV dialect detection with sampling.
Only invoked for ambiguous text files (.txt, .dat, extensionless).
"""

import logging
from pathlib import Path

from dartfx.workspace.sniffers.models import FileFormat, FileType, SnifferResult

logger = logging.getLogger(__name__)

# Maximum bytes to sample for dialect detection
MAX_SAMPLE_BYTES = 10_000

# Minimum number of lines to consider a file tabular
MIN_TABULAR_LINES = 3


def sniff_text_heuristic(file_path: Path) -> SnifferResult | None:
    """Detect if a text file contains delimited tabular data.

    Uses clevercsv for accurate dialect detection with sampling.
    Falls back to basic heuristics if clevercsv is not available.

    Returns None if the file doesn't appear to be tabular data.
    """
    try:
        with open(file_path, encoding="utf-8", errors="replace") as f:
            sample = f.read(MAX_SAMPLE_BYTES)
    except OSError:
        return None

    if not sample.strip():
        return None

    # Guard: skip structured content that is NOT tabular data
    stripped = sample.lstrip()
    if _is_structured_content(stripped):
        return None

    # Try clevercsv first for high-accuracy detection
    result = _sniff_with_clevercsv(sample)
    if result:
        return result

    # Fallback: basic delimiter detection
    return _sniff_basic(sample)


def _sniff_with_clevercsv(sample: str) -> SnifferResult | None:
    """Use clevercsv for accurate CSV dialect detection."""
    try:
        import clevercsv
    except ImportError:
        logger.debug("clevercsv not available, falling back to basic heuristics")
        return None

    try:
        dialect = clevercsv.Sniffer().sniff(sample, verbose=False)
        if dialect is None:
            return None

        delimiter = dialect.delimiter
        quotechar = dialect.quotechar or '"'

        # Reject space as delimiter — it's almost always prose, not data
        if delimiter in (" ", ""):
            return None

        # Determine format based on delimiter
        if delimiter == "\t":
            file_format = FileFormat.TSV
        else:
            file_format = FileFormat.CSV

        attributes: dict[str, str] = {"textDelimiter": delimiter}
        if quotechar:
            attributes["textQuote"] = quotechar

        return SnifferResult(
            file_type=FileType.DATA,
            file_format=file_format,
            confidence=0.85,
            attributes=attributes,
        )
    except Exception:
        logger.debug("clevercsv sniffing failed", exc_info=True)
        return None


def _sniff_basic(sample: str) -> SnifferResult | None:
    """Basic delimiter detection fallback.

    Checks if lines have consistent column counts with common delimiters.
    """
    lines = sample.strip().split("\n")
    if len(lines) < MIN_TABULAR_LINES:
        return None

    # Test common delimiters
    for delimiter, fmt in [
        (",", FileFormat.CSV),
        ("\t", FileFormat.TSV),
        ("|", FileFormat.CSV),
        (";", FileFormat.CSV),
    ]:
        counts = [len(line.split(delimiter)) for line in lines[:20]]
        if counts[0] > 1 and len(set(counts)) <= 2:  # noqa: PLR2004
            # Consistent column count across rows → likely tabular
            attributes: dict[str, str] = {"textDelimiter": delimiter}
            return SnifferResult(
                file_type=FileType.DATA,
                file_format=fmt,
                confidence=0.6,
                attributes=attributes,
            )

    return None


# Prefixes that indicate structured (non-tabular) content
_STRUCTURED_PREFIXES = (
    "<?xml",  # XML declaration
    "<!doctype",  # HTML/XML doctype
    "<html",  # HTML
    "<plist",  # Apple plist
    "@prefix",  # Turtle RDF
    "@base",  # Turtle RDF
)


def _is_structured_content(stripped: str) -> bool:
    """Check if text content appears to be structured markup or serialized data."""
    lower = stripped[:100].lower()

    # XML / HTML / plist / RDF
    for prefix in _STRUCTURED_PREFIXES:
        if lower.startswith(prefix):
            return True

    # JSON object or array
    if stripped[0] in ("{", "["):
        return True

    # YAML frontmatter
    if stripped.startswith("---"):
        return True

    return False
