"""
Data Artifex Workspace package.
"""

from dartfx.workspace.access import (
    AccessPolicy,
    QuotaExceededError,
    WorkspaceAccessDeniedError,
    WorkspacePathTraversalError,
)
from dartfx.workspace.core import Workspace
from dartfx.workspace.models import (
    AccessTier,
    Action,
    FileEntry,
    FilePreview,
    FileResource,
    FileType,
    FileTypeStats,
    Principal,
    ResourceDetail,
    SpaceConfig,
    SpaceStats,
    SparqlResult,
    TabularQueryResult,
    TaskEvent,
    TaskStatus,
    TaskType,
    TreeNode,
    Visibility,
    WorkspaceConfig,
    WorkspaceStats,
)
from dartfx.workspace.policy import (
    IngestionPolicy,
    IngestionPolicyViolationError,
    PolicyEvaluator,
    PolicyViolationError,
    RenameMode,
    RenamePolicy,
    RenamePolicyViolationError,
    WorkspaceSettings,
    ZoneRule,
)
from dartfx.workspace.spaces import Space
from dartfx.workspace.tasks import (
    detect_installed_tools,
    run_fairify_task,
    run_readstat_task,
    run_scan_task,
    run_tocsv_task,
    stream_task,
)


def hello(name: str = "World") -> str:
    """Return a greeting."""
    return f"Hello, {name}!"


__all__ = [
    "AccessPolicy",
    "AccessTier",
    "Action",
    "FileEntry",
    "FilePreview",
    "FileResource",
    "FileType",
    "FileTypeStats",
    "IngestionPolicy",
    "IngestionPolicyViolationError",
    "PolicyEvaluator",
    "PolicyViolationError",
    "Principal",
    "QuotaExceededError",
    "RenameMode",
    "RenamePolicy",
    "RenamePolicyViolationError",
    "ResourceDetail",
    "Space",
    "SpaceConfig",
    "SpaceStats",
    "SparqlResult",
    "TabularQueryResult",
    "TaskEvent",
    "TaskStatus",
    "TaskType",
    "TreeNode",
    "Visibility",
    "Workspace",
    "WorkspaceAccessDeniedError",
    "WorkspaceConfig",
    "WorkspacePathTraversalError",
    "WorkspaceSettings",
    "WorkspaceStats",
    "ZoneRule",
    "detect_installed_tools",
    "hello",
    "run_fairify_task",
    "run_readstat_task",
    "run_scan_task",
    "run_tocsv_task",
    "stream_task",
]
