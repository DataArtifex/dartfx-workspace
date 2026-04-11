"""
Workspace scanning and file profiling using BLAKE3 hashes.
"""

import uuid
from datetime import datetime
from pathlib import Path

import blake3

from dartfx.workspace.kb import KnowledgeBase
from dartfx.workspace.models import FileType


class Scanner:
    """
    Traverses the workspace, computes BLAKE3 hashes, extracts metadata,
    and classifies files using the predefined vocabulary.
    """

    def __init__(self, workspace_path: Path, kb: KnowledgeBase):
        self.workspace_path = workspace_path
        self.kb = kb
        self.ignore_dirs = {".dartfx", ".git", "__pycache__", "venv", ".venv"}

    def compute_blake3(self, file_path: Path) -> str:
        hasher = blake3.blake3()
        with open(file_path, "rb") as f:
            for chunk in iter(lambda: f.read(65536), b""):
                hasher.update(chunk)
        return hasher.hexdigest()

    def get_file_type(self, file_path: Path) -> FileType:
        """Heuristic-based categorization derived from specifications."""
        rel_path = file_path.relative_to(self.workspace_path)
        parts = rel_path.parts

        # Folder heuristics
        if len(parts) > 1:
            top_dir = parts[0].lower()
            if top_dir == "data":
                return FileType.DATA
            if top_dir in ("meta", "metadata"):
                return FileType.METADATA
            if top_dir in ("docs", "documentation"):
                return FileType.DOCUMENTATION
            if top_dir == "code":
                return FileType.CODE

        # File extension heuristics
        ext = file_path.suffix.lower()
        if ext in {".csv", ".parquet", ".json", ".sas7bdat", ".dta", ".sav"}:
            return FileType.DATA
        if ext in {".ttl", ".jsonld", ".n3", ".xml", ".yaml", ".yml"}:
            return FileType.METADATA
        if ext in {".md", ".html", ".pdf", ".docx", ".pptx", ".txt"}:
            return FileType.DOCUMENTATION
        if ext in {".py", ".java", ".js", ".r", ".sh", ".bat", ".cpp", ".rs"}:
            return FileType.CODE

        return FileType.OTHER

    def scan(self):
        """Scans the workspace and synchronizes with the Knowledge Base."""
        existing_files = self.kb.get_all_files()
        existing_path_map = {f["path"]: f for f in existing_files}
        existing_hash_map = {f["blake3_hash"]: f for f in existing_files}

        current_paths = set()

        for p in self.workspace_path.rglob("*"):
            if not p.is_file():
                continue

            # Skip ignored directories or hidden files/dirs
            rel_parts = p.relative_to(self.workspace_path).parts
            if any(part.startswith(".") or part in self.ignore_dirs for part in rel_parts):
                continue

            rel_path_str = p.relative_to(self.workspace_path).as_posix()
            current_paths.add(rel_path_str)

            try:
                stat = p.stat()
                size = stat.st_size
                created = datetime.fromtimestamp(stat.st_ctime)
                updated = datetime.fromtimestamp(stat.st_mtime)
                b3hash = self.compute_blake3(p)
            except Exception as e:
                # Handle unexpected file reading errors gracefully
                print(f"Skipping {p}: {e}")
                continue

            file_type = self.get_file_type(p).value

            if rel_path_str in existing_path_map:
                old_f = existing_path_map[rel_path_str]
                if old_f["blake3_hash"] != b3hash or old_f["size_bytes"] != size:
                    self.kb.upsert_file_resource(
                        uuid.UUID(old_f["uuid"]),
                        p.relative_to(self.workspace_path),
                        size,
                        b3hash,
                        file_type,
                        created,
                        updated,
                    )
            else:
                # Path not tracked, check if renamed
                uuid_to_use = uuid.uuid4()
                if b3hash in existing_hash_map:
                    suspected_old_file = existing_hash_map[b3hash]
                    old_path_p = self.workspace_path / suspected_old_file["path"]
                    if not old_path_p.exists():
                        # It's a rename! Recover the UUID
                        uuid_to_use = uuid.UUID(suspected_old_file["uuid"])
                        del existing_hash_map[b3hash]

                self.kb.upsert_file_resource(
                    uuid_to_use, p.relative_to(self.workspace_path), size, b3hash, file_type, created, updated
                )

        self.kb.save()

        # Phase 2: Cleanup missing files
        updated_kb_files = self.kb.get_all_files()
        for f in updated_kb_files:
            if f["path"] not in current_paths:
                self.kb.remove_file_resource(uuid.UUID(f["uuid"]))

        self.kb.save()
