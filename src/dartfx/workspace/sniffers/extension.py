"""
Step 1: Extension-based classifier.

Zero I/O — resolves type and format from file extension and folder heuristics.
"""

from pathlib import Path

from dartfx.workspace.sniffers.models import FileFormat, FileType, SnifferResult

# Extension → (FileType, FileFormat) mapping
# Ambiguous extensions (e.g. .txt, .dat) are NOT included here;
# they fall through to content-based sniffers.
EXTENSION_MAP: dict[str, tuple[FileType, FileFormat]] = {
    # Data formats
    ".csv": (FileType.DATA, FileFormat.CSV),
    ".tsv": (FileType.DATA, FileFormat.TSV),
    ".parquet": (FileType.DATA, FileFormat.PARQUET),
    ".sas7bdat": (FileType.DATA, FileFormat.SAS7BDAT),
    ".sas7bcat": (FileType.METADATA, FileFormat.SAS7BCAT),
    ".dta": (FileType.DATA, FileFormat.DTA),
    ".sav": (FileType.DATA, FileFormat.SAV),
    ".xlsx": (FileType.DATA, FileFormat.XLSX),
    ".xls": (FileType.DATA, FileFormat.XLS),
    # Metadata formats — JSON is metadata by default in this domain
    ".json": (FileType.METADATA, FileFormat.JSON),
    ".jsonl": (FileType.DATA, FileFormat.JSONL),
    ".jsonld": (FileType.METADATA, FileFormat.JSONLD),
    ".ttl": (FileType.METADATA, FileFormat.TURTLE),
    ".n3": (FileType.METADATA, FileFormat.N3),
    ".xml": (FileType.METADATA, FileFormat.XML),
    ".yaml": (FileType.METADATA, FileFormat.YAML),
    ".yml": (FileType.METADATA, FileFormat.YAML),
    # Documentation formats
    ".md": (FileType.DOCUMENTATION, FileFormat.MARKDOWN),
    ".html": (FileType.DOCUMENTATION, FileFormat.HTML),
    ".htm": (FileType.DOCUMENTATION, FileFormat.HTML),
    ".pdf": (FileType.DOCUMENTATION, FileFormat.PDF),
    ".docx": (FileType.DOCUMENTATION, FileFormat.DOCX),
    ".pptx": (FileType.DOCUMENTATION, FileFormat.PPTX),
    # Code formats
    ".py": (FileType.CODE, FileFormat.PYTHON),
    ".r": (FileType.CODE, FileFormat.R),
    ".sas": (FileType.CODE, FileFormat.SAS_SYNTAX),
    ".do": (FileType.CODE, FileFormat.STATA_SYNTAX),
    ".sps": (FileType.CODE, FileFormat.SPSS_SYNTAX),
    ".sql": (FileType.CODE, FileFormat.SQL),
    ".sh": (FileType.CODE, FileFormat.SHELL),
    ".bat": (FileType.CODE, FileFormat.SHELL),
    ".cmd": (FileType.CODE, FileFormat.SHELL),
    ".js": (FileType.CODE, FileFormat.JAVASCRIPT),
    ".java": (FileType.CODE, FileFormat.JAVA),
    ".cpp": (FileType.CODE, FileFormat.CPP),
    ".c": (FileType.CODE, FileFormat.CPP),
    ".h": (FileType.CODE, FileFormat.CPP),
    ".rs": (FileType.CODE, FileFormat.RUST),
    # Compressed / archive formats
    ".zip": (FileType.COMPRESSED, FileFormat.ZIP),
    ".7z": (FileType.COMPRESSED, FileFormat.SEVENZ),
    ".rar": (FileType.COMPRESSED, FileFormat.RAR),
    ".gz": (FileType.COMPRESSED, FileFormat.GZIP),
    ".gzip": (FileType.COMPRESSED, FileFormat.GZIP),
    ".bz2": (FileType.COMPRESSED, FileFormat.BZIP2),
    ".xz": (FileType.COMPRESSED, FileFormat.XZ),
    ".br": (FileType.COMPRESSED, FileFormat.BROTLI),
    ".zst": (FileType.COMPRESSED, FileFormat.ZSTD),
    ".tar": (FileType.COMPRESSED, FileFormat.TAR),
    ".tgz": (FileType.COMPRESSED, FileFormat.GZIP),
    ".tar.gz": (FileType.COMPRESSED, FileFormat.GZIP),
    ".tar.bz2": (FileType.COMPRESSED, FileFormat.BZIP2),
    ".tar.xz": (FileType.COMPRESSED, FileFormat.XZ),
    # Media formats — images
    ".png": (FileType.MEDIA, FileFormat.PNG),
    ".jpg": (FileType.MEDIA, FileFormat.JPEG),
    ".jpeg": (FileType.MEDIA, FileFormat.JPEG),
    ".gif": (FileType.MEDIA, FileFormat.GIF),
    ".svg": (FileType.MEDIA, FileFormat.SVG),
    ".webp": (FileType.MEDIA, FileFormat.WEBP),
    ".tiff": (FileType.MEDIA, FileFormat.TIFF),
    ".tif": (FileType.MEDIA, FileFormat.TIFF),
    ".bmp": (FileType.MEDIA, FileFormat.BMP),
    ".ico": (FileType.MEDIA, FileFormat.ICO),
    # Media formats — video
    ".mp4": (FileType.MEDIA, FileFormat.MP4),
    ".avi": (FileType.MEDIA, FileFormat.AVI),
    ".mkv": (FileType.MEDIA, FileFormat.MKV),
    ".mov": (FileType.MEDIA, FileFormat.MOV),
    ".webm": (FileType.MEDIA, FileFormat.WEBM),
    ".wmv": (FileType.MEDIA, FileFormat.WMV),
    # Media formats — audio
    ".mp3": (FileType.MEDIA, FileFormat.MP3),
    ".wav": (FileType.MEDIA, FileFormat.WAV),
    ".flac": (FileType.MEDIA, FileFormat.FLAC),
    ".ogg": (FileType.MEDIA, FileFormat.OGG),
    ".aac": (FileType.MEDIA, FileFormat.AAC),
    ".wma": (FileType.MEDIA, FileFormat.WMA),
}

# Ambiguous extensions that need content-based sniffing
AMBIGUOUS_EXTENSIONS: set[str] = {".txt", ".dat"}


def _qsv_fairify_metadata_override(file_path: Path) -> SnifferResult | None:
    """Classify known qsv/fairify artifacts as metadata.

    Some qsv/fairify outputs intentionally reuse data-looking extensions
    (e.g. ``freq.csv``), but semantically represent profiling metadata.
    """
    name = file_path.name.lower()
    parent_name = file_path.parent.name.lower()

    # Direct artifact names/suffixes produced by qsv/fairify.
    if (
        name == "freq.csv"
        or name.endswith(".freqs.csv")
        or name.endswith(".freq.long.csv")
        or name.endswith(".freqs.long.csv")
        or name.endswith(".stats.csv")
        or name.endswith(".stats.csv.data.jsonl")
        or name.endswith(".stats.csv.json")
    ):
        return SnifferResult(
            file_type=FileType.METADATA,
            file_format=(
                FileFormat.JSON
                if name.endswith(".json")
                else FileFormat.JSONL
                if name.endswith(".jsonl")
                else FileFormat.CSV
            ),
            confidence=0.95,
        )

    # stats CSV can be emitted as a folder containing JSON payload.
    if name == "data.json" and parent_name.endswith(".stats.csv"):
        return SnifferResult(
            file_type=FileType.METADATA,
            file_format=FileFormat.JSON,
            confidence=0.95,
        )

    # qsv index sidecar files should be treated as metadata as well.
    if name.endswith(".csv.idx"):
        return SnifferResult(
            file_type=FileType.METADATA,
            file_format=FileFormat.UNDETERMINED,
            confidence=0.95,
        )

    return None


def classify_by_extension(
    file_path: Path,
) -> SnifferResult | None:
    """Classify a file by its extension.

    Returns None if the extension is ambiguous or unrecognized, signaling
    that content-based sniffers should take over for classification.
    Returns a SnifferResult if the extension is unambiguous.
    """
    ext = file_path.suffix.lower()

    # Known tool-generated artifacts get domain-specific classification first.
    qsv_override = _qsv_fairify_metadata_override(file_path)
    if qsv_override is not None:
        return qsv_override

    # Ambiguous extensions → signal content sniffing needed
    if ext in AMBIGUOUS_EXTENSIONS or ext == "":
        return None

    # Known extension → resolve immediately
    if ext in EXTENSION_MAP:
        file_type, file_format = EXTENSION_MAP[ext]
        return SnifferResult(
            file_type=file_type,
            file_format=file_format,
            confidence=0.9,
        )

    # Unrecognized extension
    return SnifferResult(
        file_type=FileType.OTHER,
        file_format=FileFormat.UNDETERMINED,
        confidence=0.2,
    )
