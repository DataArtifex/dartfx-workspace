"""
Core workspace management module.
"""

import os
from pathlib import Path

from dartfx.workspace.kb import KnowledgeBase
from dartfx.workspace.models import FileType, WorkspaceStats
from dartfx.workspace.scanner import Scanner


class Workspace:
    """
    Facade for managing workspace initialization and orchestrating
    scans and Knowledge Base interactions.
    """

    def __init__(self, path: Path | None = None):
        self.path = path or Path(os.getcwd())
        self.path = self.path.resolve()

        # Check environment variable first before falling back to .dartfx as per specs
        env_dir = os.environ.get("DARTFX_WORKSPACE_DIR", ".dartfx")
        self.dartfx_dir = self.path / env_dir

        self._kb: KnowledgeBase | None = None
        self._scanner: Scanner | None = None

    @classmethod
    def init(cls, path: Path | None = None, create_dirs: bool = False) -> "Workspace":
        ws = cls(path)
        ws.dartfx_dir.mkdir(parents=True, exist_ok=True)
        if create_dirs:
            # Create standard folders
            for folder in ["code", "docs", "data", "meta", "work"]:
                (ws.path / folder).mkdir(exist_ok=True)
        return ws

    def is_initialized(self) -> bool:
        return self.dartfx_dir.exists() and self.dartfx_dir.is_dir()

    @property
    def kb(self) -> KnowledgeBase:
        if not self.is_initialized():
            raise RuntimeError("Workspace is not initialized. Run `workspace init` first.")
        if not self._kb:
            self._kb = KnowledgeBase(self.path)
        return self._kb

    @property
    def scanner(self) -> Scanner:
        if not self.is_initialized():
            raise RuntimeError("Workspace is not initialized. Run `workspace init` first.")
        if not self._scanner:
            self._scanner = Scanner(self.path, self.kb)
        return self._scanner

    def scan(self):
        """Triggers a filesystem scan and KB synchronization."""
        self.scanner.scan()

    def stats(self) -> WorkspaceStats:
        """Computes stats based on the latest knowledge base data and filesystem probe."""
        # 1. Get registered files from KB
        kb_files = self.kb.get_all_files()
        registered_paths = {f["path"] for f in kb_files}

        # 2. Get all files from filesystem (excluding ignored)
        all_fs_files = []
        ignore_dirs = {".dartfx", ".git", "__pycache__", "venv", ".venv"}
        for p in self.path.rglob("*"):
            if not p.is_file():
                continue
            rel_parts = p.relative_to(self.path).parts
            if any(part.startswith(".") or part in ignore_dirs for part in rel_parts):
                continue
            all_fs_files.append(p)

        # 3. Calculate metrics
        from dartfx.workspace.models import FileTypeStats  # Importing here to avoid potential circular if any

        types_info = {t: FileTypeStats() for t in FileType}
        reg_count = 0
        reg_size = 0
        unreg_count = 0
        unreg_size = 0

        # Aggregate registered
        for f in kb_files:
            type_str = f["type"]
            size = f["size_bytes"]
            reg_count += 1
            reg_size += size
            try:
                type_enum = FileType(type_str)
            except ValueError:
                type_enum = FileType.OTHER

            types_info[type_enum].count += 1
            types_info[type_enum].size_bytes += size

        # Aggregate unregistered
        for p in all_fs_files:
            rel_path = p.relative_to(self.path).as_posix()
            if rel_path not in registered_paths:
                unreg_count += 1
                unreg_size += p.stat().st_size

        return WorkspaceStats(
            total_files=reg_count + unreg_count,
            total_size_bytes=reg_size + unreg_size,
            registered_count=reg_count,
            registered_size_bytes=reg_size,
            unregistered_count=unreg_count,
            unregistered_size_bytes=unreg_size,
            types_info=types_info,
        )
