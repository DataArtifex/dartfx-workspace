"""
Pydantic models for dartfx-workspace.
"""

from datetime import datetime
from pathlib import Path
from uuid import UUID

from pydantic import BaseModel, Field

from dartfx.workspace.sniffers import FileFormat, FileType


class FileResource(BaseModel):
    """
    Metadata representation of a file resource in the workspace.
    Maintains a stable UUID that persists across renames/moves within the workspace.
    """

    id: UUID = Field(description="Stable URI component for the RDF Knowledge Base (urn:uuid:<id>)")
    path: Path = Field(description="Relative path of the file to the workspace root")
    size_bytes: int = Field(description="File size in bytes")
    created_at: datetime = Field(description="File creation timestamp")
    updated_at: datetime = Field(description="File last modification timestamp")
    blake3_hash: str = Field(description="BLAKE3 hash string for file integrity and deduplication/rename tracking")
    type: FileType = Field(default=FileType.OTHER, description="Controlled vocabulary type of the file")
    file_format: FileFormat = Field(default=FileFormat.UNDETERMINED, description="Specific detected file format")


class FileTypeStats(BaseModel):
    count: int = 0
    size_bytes: int = 0


class WorkspaceStats(BaseModel):
    """
    Aggregation statistics for a workspace.
    """

    total_files: int
    total_size_bytes: int
    registered_count: int
    registered_size_bytes: int
    unregistered_count: int
    unregistered_size_bytes: int
    types_info: dict[FileType, FileTypeStats]
