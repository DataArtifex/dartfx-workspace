"""
Programmatic 3-tier access policy and quota enforcement for dartfx-workspace.
"""

from dartfx.workspace.models import (
    AccessTier,
    Action,
    Principal,
    SpaceConfig,
    Visibility,
    WorkspaceConfig,
)


class WorkspaceAccessDeniedError(PermissionError):
    """Raised when a principal lacks permission for an action on a workspace or space."""


class QuotaExceededError(ValueError):
    """Raised when an operation would exceed a workspace or space storage quota."""


class WorkspacePathTraversalError(ValueError):
    """Raised when a requested path attempts to escape the workspace root or access restricted internals."""


class AccessPolicy:
    """Evaluates 3-tier authorization and storage quota policies."""

    @staticmethod
    def can_access_space(principal: Principal, space_config: SpaceConfig, action: Action) -> bool:
        """Return whether the principal is allowed to perform an action on a Space."""
        if principal.tier == AccessTier.ADMIN:
            return True

        if action == Action.ADMIN:
            return False

        if space_config.visibility == Visibility.PUBLIC:
            return True

        if principal.tier == AccessTier.ANONYMOUS:
            return False

        if space_config.id in principal.allowed_space_ids:
            return True

        return False

    @staticmethod
    def can_access_workspace(principal: Principal, ws_config: WorkspaceConfig, action: Action) -> bool:
        """Return whether the principal is allowed to perform an action on a Workspace."""
        if principal.tier == AccessTier.ADMIN:
            return True

        if action == Action.ADMIN:
            return False

        if ws_config.visibility == Visibility.PUBLIC:
            return True

        if principal.tier == AccessTier.ANONYMOUS:
            return False

        # AccessTier.USER rules
        if ws_config.visibility == Visibility.PRIVATE:
            return ws_config.owner_id in (None, principal.id)

        if ws_config.visibility == Visibility.TEAM:
            if ws_config.owner_id == principal.id:
                return True
            if ws_config.team_id and ws_config.team_id in principal.team_ids:
                return True
            if ws_config.space_id and ws_config.space_id in principal.allowed_space_ids:
                return True
            return False

        return False

    @classmethod
    def authorize(cls, principal: Principal, ws_config: WorkspaceConfig, action: Action) -> None:
        """Verify authorization or raise WorkspaceAccessDeniedError."""
        if not cls.can_access_workspace(principal, ws_config, action):
            raise WorkspaceAccessDeniedError(
                f"Principal '{principal.id}' (tier={principal.tier.value}) is not authorized "
                f"for '{action.value}' on workspace '{ws_config.id}'."
            )

    @classmethod
    def authorize_space(cls, principal: Principal, space_config: SpaceConfig, action: Action) -> None:
        """Verify space authorization or raise WorkspaceAccessDeniedError."""
        if not cls.can_access_space(principal, space_config, action):
            raise WorkspaceAccessDeniedError(
                f"Principal '{principal.id}' (tier={principal.tier.value}) is not authorized "
                f"for '{action.value}' on space '{space_config.id}'."
            )

    @staticmethod
    def check_quota(current_bytes: int, additional_bytes: int, quota_bytes: int | None) -> None:
        """Ensure adding additional_bytes does not exceed quota_bytes."""
        if quota_bytes is None:
            return
        if (current_bytes + max(0, additional_bytes)) > quota_bytes:
            raise QuotaExceededError(
                f"Storage quota exceeded: current={current_bytes}B, incoming={additional_bytes}B, quota={quota_bytes}B."
            )
