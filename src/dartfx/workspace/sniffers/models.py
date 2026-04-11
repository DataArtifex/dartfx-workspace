"""
Self-contained data models for file type sniffing.

No dependencies on dartfx-workspace internals.
"""

from dataclasses import dataclass, field
from enum import StrEnum


class FileType(StrEnum):
    """Broad file classification category."""

    DATA = "data"
    METADATA = "metadata"
    DOCUMENTATION = "documentation"
    CODE = "code"
    COMPRESSED = "compressed"
    MEDIA = "media"
    OTHER = "other"


class FileFormat(StrEnum):
    """Specific file format identifier."""

    # Data formats
    CSV = "csv"
    TSV = "tsv"
    FIXED_WIDTH = "fixed-width"
    PARQUET = "parquet"
    JSON = "json"
    SAS7BDAT = "sas7bdat"
    DTA = "dta"
    SAV = "sav"
    XLSX = "xlsx"
    XLS = "xls"
    SAS7BCAT = "sas7bcat"

    # Metadata formats
    TURTLE = "turtle"
    JSONLD = "jsonld"
    N3 = "n3"
    XML = "xml"
    YAML = "yaml"

    # Documentation formats
    MARKDOWN = "markdown"
    HTML = "html"
    PDF = "pdf"
    DOCX = "docx"
    PPTX = "pptx"
    TEXT = "text"

    # Code formats
    PYTHON = "python"
    R = "r"
    SAS_SYNTAX = "sas-syntax"
    STATA_SYNTAX = "stata-syntax"
    SPSS_SYNTAX = "spss-syntax"
    SHELL = "shell"
    JAVASCRIPT = "javascript"
    JAVA = "java"
    CPP = "cpp"
    RUST = "rust"

    # Compressed / archive formats
    ZIP = "zip"
    SEVENZ = "7z"
    RAR = "rar"
    GZIP = "gzip"
    BZIP2 = "bzip2"
    XZ = "xz"
    BROTLI = "brotli"
    ZSTD = "zstd"
    TAR = "tar"

    # Media formats — images
    PNG = "png"
    JPEG = "jpeg"
    GIF = "gif"
    SVG = "svg"
    WEBP = "webp"
    TIFF = "tiff"
    BMP = "bmp"
    ICO = "ico"

    # Media formats — video
    MP4 = "mp4"
    AVI = "avi"
    MKV = "mkv"
    MOV = "mov"
    WEBM = "webm"
    WMV = "wmv"

    # Media formats — audio
    MP3 = "mp3"
    WAV = "wav"
    FLAC = "flac"
    OGG = "ogg"
    AAC = "aac"
    WMA = "wma"

    # Fallback
    UNDETERMINED = "undetermined"


MIME_TYPE_MAP: dict[FileFormat, str] = {
    FileFormat.CSV: "text/csv",
    FileFormat.TSV: "text/tab-separated-values",
    FileFormat.PARQUET: "application/vnd.apache.parquet",
    FileFormat.JSON: "application/json",
    FileFormat.JSONLD: "application/ld+json",
    FileFormat.SAS7BDAT: "application/x-sas-data",
    FileFormat.DTA: "application/x-stata-dta",
    FileFormat.SAV: "application/x-spss-sav",
    FileFormat.SAS7BCAT: "application/x-sas-catalog",
    FileFormat.XLSX: "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    FileFormat.XLS: "application/vnd.ms-excel",
    FileFormat.TURTLE: "text/turtle",
    FileFormat.N3: "text/n3",
    FileFormat.XML: "application/xml",
    FileFormat.YAML: "application/yaml",
    FileFormat.MARKDOWN: "text/markdown",
    FileFormat.HTML: "text/html",
    FileFormat.PDF: "application/pdf",
    FileFormat.DOCX: "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    FileFormat.PPTX: "application/vnd.openxmlformats-officedocument.presentationml.presentation",
    FileFormat.TEXT: "text/plain",
    FileFormat.PYTHON: "text/x-python",
    FileFormat.R: "text/x-r",
    FileFormat.SAS_SYNTAX: "text/x-sas",
    FileFormat.STATA_SYNTAX: "text/x-stata",
    FileFormat.SPSS_SYNTAX: "text/x-spss",
    FileFormat.SHELL: "text/x-shellscript",
    FileFormat.JAVASCRIPT: "text/javascript",
    FileFormat.JAVA: "text/x-java",
    FileFormat.CPP: "text/x-c++src",
    FileFormat.RUST: "text/x-rustsrc",
    FileFormat.ZIP: "application/zip",
    FileFormat.SEVENZ: "application/x-7z-compressed",
    FileFormat.RAR: "application/vnd.rar",
    FileFormat.GZIP: "application/gzip",
    FileFormat.BZIP2: "application/x-bzip2",
    FileFormat.XZ: "application/x-xz",
    FileFormat.BROTLI: "application/x-brotli",
    FileFormat.ZSTD: "application/zstd",
    FileFormat.TAR: "application/x-tar",
    FileFormat.PNG: "image/png",
    FileFormat.JPEG: "image/jpeg",
    FileFormat.GIF: "image/gif",
    FileFormat.SVG: "image/svg+xml",
    FileFormat.WEBP: "image/webp",
    FileFormat.TIFF: "image/tiff",
    FileFormat.BMP: "image/bmp",
    FileFormat.ICO: "image/x-icon",
    FileFormat.MP4: "video/mp4",
    FileFormat.AVI: "video/x-msvideo",
    FileFormat.MKV: "video/x-matroska",
    FileFormat.MOV: "video/quicktime",
    FileFormat.WEBM: "video/webm",
    FileFormat.WMV: "video/x-ms-wmv",
    FileFormat.MP3: "audio/mpeg",
    FileFormat.WAV: "audio/wav",
    FileFormat.FLAC: "audio/flac",
    FileFormat.OGG: "audio/ogg",
    FileFormat.AAC: "audio/aac",
    FileFormat.WMA: "audio/x-ms-wma",
}


@dataclass
class SnifferResult:
    """Result of a file sniffing operation."""

    file_type: FileType
    file_format: FileFormat
    mime_type: str | None = None
    confidence: float = 1.0
    attributes: dict[str, str] = field(default_factory=dict)

    def display_label(self) -> str:
        """Human-readable label for shell display (e.g. 'data/csv')."""
        if self.file_format == FileFormat.UNDETERMINED:
            return self.file_type.value
        return f"{self.file_type.value}/{self.file_format.value}"
