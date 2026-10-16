"""Workspace membership resolution kept separate from token authentication."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, Protocol
from uuid import UUID

from evidence_service.auth import Principal

WorkspaceRole = Literal["owner", "member"]


@dataclass(frozen=True)
class WorkspaceMembership:
    workspace_id: UUID
    workspace_name: str
    role: WorkspaceRole


@dataclass(frozen=True)
class WorkspaceContext:
    workspace_id: UUID
    workspace_name: str
    role: WorkspaceRole


class WorkspaceAccessDenied(Exception):
    """No active membership grants access to the selected workspace."""


class WorkspaceDirectory(Protocol):
    async def list_memberships(
        self, principal: Principal, access_token: str
    ) -> list[WorkspaceMembership]: ...

    async def get_membership(
        self, principal: Principal, access_token: str, workspace_id: UUID
    ) -> WorkspaceMembership | None: ...


async def resolve_workspace_context(
    directory: WorkspaceDirectory,
    principal: Principal,
    access_token: str,
    workspace_id: UUID,
) -> WorkspaceContext:
    """Resolve a client-selected workspace only through verified membership."""
    membership = await directory.get_membership(principal, access_token, workspace_id)
    if membership is None:
        raise WorkspaceAccessDenied
    return WorkspaceContext(
        workspace_id=membership.workspace_id,
        workspace_name=membership.workspace_name,
        role=membership.role,
    )
