"""HTTP application for health, verified identity, and workspace boundaries."""

from __future__ import annotations

from typing import Literal
from uuid import UUID

from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel

from evidence_service.auth import (
    AuthenticatedRequest,
    AuthenticationRejected,
    AuthenticationUnavailable,
    SupabaseTokenVerifier,
    TokenVerifier,
)
from evidence_service.config import ConfigurationError, SupabaseSettings
from evidence_service.supabase_repository import (
    SupabaseWorkspaceRepository,
    WorkspaceDataUnavailable,
)
from evidence_service.tenant_context import (
    WorkspaceAccessDenied,
    WorkspaceDirectory,
    resolve_workspace_context,
)


class WorkspaceSummary(BaseModel):
    id: UUID
    name: str
    role: Literal["owner", "member"]


class MeResponse(BaseModel):
    user_id: UUID
    issuer: str
    workspaces: list[WorkspaceSummary]


class WorkspaceResponse(BaseModel):
    id: UUID
    name: str
    role: Literal["owner", "member"]


bearer_scheme = HTTPBearer(auto_error=False)


def _settings_for(request: Request) -> SupabaseSettings:
    settings = request.app.state.supabase_settings
    if settings is not None:
        return settings
    try:
        settings = SupabaseSettings.from_environment()
    except ConfigurationError as exc:
        raise HTTPException(
            status_code=503, detail="Identity service is not configured"
        ) from exc
    request.app.state.supabase_settings = settings
    return settings


async def require_authenticated_request(
    request: Request,
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
) -> AuthenticatedRequest:
    if credentials is None or credentials.scheme.lower() != "bearer":
        raise HTTPException(
            status_code=401,
            detail="A valid bearer access token is required",
            headers={"WWW-Authenticate": "Bearer"},
        )

    settings = _settings_for(request)
    verifier = request.app.state.token_verifier
    if verifier is None:
        verifier = SupabaseTokenVerifier(settings)
        request.app.state.token_verifier = verifier

    try:
        principal = await verifier.verify(credentials.credentials)
    except AuthenticationRejected as exc:
        raise HTTPException(
            status_code=401,
            detail="Invalid bearer access token",
            headers={"WWW-Authenticate": "Bearer"},
        ) from exc
    except AuthenticationUnavailable as exc:
        raise HTTPException(
            status_code=503, detail="Identity verification is unavailable"
        ) from exc

    return AuthenticatedRequest(principal, credentials.credentials)


def _workspace_directory(request: Request) -> WorkspaceDirectory:
    directory = request.app.state.workspace_directory
    if directory is None:
        directory = SupabaseWorkspaceRepository(_settings_for(request))
        request.app.state.workspace_directory = directory
    return directory


def create_app(
    settings: SupabaseSettings | None = None,
    *,
    token_verifier: TokenVerifier | None = None,
    workspace_directory: WorkspaceDirectory | None = None,
) -> FastAPI:
    """Create the service app; optional integrations are initialized on demand."""
    application = FastAPI(
        title="Evidence Layer identity service",
        docs_url=None,
        redoc_url=None,
        openapi_url=None,
    )
    application.state.supabase_settings = settings
    application.state.token_verifier = token_verifier
    application.state.workspace_directory = workspace_directory

    @application.api_route(
        "/healthz", methods=["GET"], status_code=200, include_in_schema=False
    )
    async def healthz() -> dict[str, str]:
        return {"status": "ok"}

    @application.get("/v1/me", response_model=MeResponse)
    async def me(
        request: Request,
        auth: AuthenticatedRequest = Depends(require_authenticated_request),
    ) -> MeResponse:
        try:
            memberships = await _workspace_directory(request).list_memberships(
                auth.principal, auth.access_token
            )
        except WorkspaceDataUnavailable as exc:
            raise HTTPException(
                status_code=503, detail="Workspace directory is unavailable"
            ) from exc

        return MeResponse(
            user_id=auth.principal.subject,
            issuer=auth.principal.issuer,
            workspaces=[
                WorkspaceSummary(
                    id=membership.workspace_id,
                    name=membership.workspace_name,
                    role=membership.role,
                )
                for membership in memberships
            ],
        )

    @application.get("/v1/workspaces/{workspace_id}", response_model=WorkspaceResponse)
    async def get_workspace(
        workspace_id: UUID,
        request: Request,
        auth: AuthenticatedRequest = Depends(require_authenticated_request),
    ) -> WorkspaceResponse:
        try:
            context = await resolve_workspace_context(
                _workspace_directory(request),
                auth.principal,
                auth.access_token,
                workspace_id,
            )
        except WorkspaceAccessDenied as exc:
            raise HTTPException(status_code=404, detail="Workspace not found") from exc
        except WorkspaceDataUnavailable as exc:
            raise HTTPException(
                status_code=503, detail="Workspace directory is unavailable"
            ) from exc

        return WorkspaceResponse(
            id=context.workspace_id,
            name=context.workspace_name,
            role=context.role,
        )

    return application


app = create_app()
