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
