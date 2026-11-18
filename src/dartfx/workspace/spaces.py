"""
Space and ephemeral sandbox workspace management for dartfx-workspace.
"""

import json
import shutil
from pathlib import Path

from dartfx.workspace.access import AccessPolicy
from dartfx.workspace.core import Workspace
from dartfx.workspace.models import SpaceConfig, SpaceStats

_SAMPLE_SURVEY_CSV = """respondent_id,region,age_group,income_usd,satisfaction
1001,North,25-34,62000,4
1002,South,35-44,78500,5
1003,East,18-24,41000,3
1004,West,45-54,94000,5
1005,North,55+,83000,4
1006,South,25-34,58000,4
"""

_SAMPLE_DOCS_README = """# Public Sandbox Workspace

Welcome to the **Data Artifex Public Sandbox Workspace**.

This ephemeral workspace follows the standard FAIR workspace directory layout:
- `data/`: observation-level microdata and tabular datasets
- `meta/`: machine-actionable metadata catalogs and schemas
- `docs/`: human-readable documentation
- `code/`: transformation and QA scripts
- `work/`: transient intermediate outputs
- `prod/`: publication-ready data products
"""

_SAMPLE_CATALOG_JSON = {
    "@context": "https://schema.org/",
    "@type": "Dataset",
    "name": "Sample Household Survey",
    "description": "Ephemeral demonstration dataset for exploring dartfx-workspace capabilities.",
    "distribution": [
        {
            "@type": "DataDownload",
            "contentUrl": "data/sample_survey.csv",
            "encodingFormat": "text/csv",
        }
    ],
}


def _compute_dir_usage_bytes(root: Path) -> int:
    """Compute cumulative byte size of non-hidden user files under root."""
    if not root.exists():
        return 0
    ignore_dirs = {".dartfx", ".git", "__pycache__", "venv", ".venv"}
    total = 0
    for item in root.rglob("*"):
        if not item.is_file():
            continue
        rel_parts = item.relative_to(root).parts
        if any(part.startswith(".") or part in ignore_dirs for part in rel_parts):
            continue
        try:
            total += item.stat().st_size
        except OSError:
            continue
    return total


class Space:
    """Virtual storage area grouping workspaces and enforcing aggregate storage quotas."""

    def __init__(self, config: SpaceConfig):
        self.config = config
        self.root_path = config.root_path.resolve()

    def total_usage_bytes(self, workspaces: list[Workspace] | None = None) -> int:
        """Compute total user-file storage used across workspaces or the space root."""
        if workspaces is not None:
            return sum(ws.stats().total_size_bytes for ws in workspaces)
        return _compute_dir_usage_bytes(self.root_path)

    def stats(self, workspaces: list[Workspace]) -> SpaceStats:
        """Compute aggregate SpaceStats across the given workspaces."""
        total_files = 0
        total_size_bytes = 0
        for ws in workspaces:
            if ws.is_initialized():
                ws_stats = ws.stats()
                total_files += ws_stats.total_files
                total_size_bytes += ws_stats.total_size_bytes
            else:
                total_size_bytes += _compute_dir_usage_bytes(ws.path)

        quota = self.config.storage_quota_bytes
        used_pct: float | None = None
        if quota is not None and quota > 0:
            used_pct = round((total_size_bytes / quota) * 100.0, 2)

        return SpaceStats(
            space_id=self.config.id,
            workspace_count=len(workspaces),
            total_files=total_files,
            total_size_bytes=total_size_bytes,
            storage_quota_bytes=quota,
            quota_used_pct=used_pct,
        )

    def check_space_quota(self, additional_bytes: int, current_used: int | None = None) -> None:
        """Validate that adding additional_bytes does not breach the Space quota."""
        used = self.total_usage_bytes() if current_used is None else current_used
        AccessPolicy.check_quota(used, additional_bytes, self.config.storage_quota_bytes)

    @classmethod
    def provision_ephemeral_workspace(cls, path: Path, sample_files: bool = True) -> Workspace:
        """Initialize an ephemeral sandbox workspace with standard folders and sample assets."""
        target = path.resolve()
        target.mkdir(parents=True, exist_ok=True)
        ws = Workspace.init(target, create_dirs=True)
        (ws.path / "prod").mkdir(exist_ok=True)

        if sample_files:
            (ws.path / "data" / "sample_survey.csv").write_text(_SAMPLE_SURVEY_CSV, encoding="utf-8")
            (ws.path / "docs" / "README.md").write_text(_SAMPLE_DOCS_README, encoding="utf-8")
            (ws.path / "meta" / "catalog.json").write_text(
                json.dumps(_SAMPLE_CATALOG_JSON, indent=2) + "\n", encoding="utf-8"
            )

        ws.scan()
        return ws

    @classmethod
    def reset_ephemeral_workspace(cls, path: Path, sample_files: bool = True) -> Workspace:
        """Wipe and re-provision an ephemeral workspace from scratch."""
        target = path.resolve()
        if target.exists():
            shutil.rmtree(target)
        return cls.provision_ephemeral_workspace(target, sample_files=sample_files)
