from __future__ import annotations

import asyncio
import uuid

import httpx
import pytest

from evidence_service.auth import Principal
from evidence_service.config import SupabaseSettings
from evidence_service.supabase_repository import (
    SupabaseWorkspaceRepository,
    WorkspaceDataUnavailable,
)


SUBJECT = uuid.UUID("10000000-0000-4000-8000-000000000001")
WORKSPACE = uuid.UUID("a1000000-0000-4000-8000-000000000001")
TOKEN = "verified.synthetic.jwt"


def settings() -> SupabaseSettings:
    return SupabaseSettings(
        supabase_url="https://project-ref.supabase.co",
        publishable_key="sb_publishable_synthetic_test_key",
        jwt_issuer="https://project-ref.supabase.co/auth/v1",
        jwt_audience="authenticated",
        jwt_algorithms=("RS256",),
    )


def test_membership_query_uses_verified_user_token_and_no_admin_key() -> None:
    observed: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        observed.append(request)
        return httpx.Response(
            200,
            json=[
                {
                    "user_id": str(SUBJECT),
                    "workspace_id": str(WORKSPACE),
                    "role": "owner",
                    "workspace": {"id": str(WORKSPACE), "name": "A primary"},
                }
            ],
        )

    repository = SupabaseWorkspaceRepository(
        settings(), transport=httpx.MockTransport(handler)
    )
    result = asyncio.run(
        repository.list_memberships(Principal(settings().jwt_issuer, SUBJECT), TOKEN)
    )

    request = observed[0]
    assert request.url.path == "/rest/v1/workspace_memberships"
    assert request.url.params["user_id"] == f"eq.{SUBJECT}"
    assert request.url.params["status"] == "eq.active"
    assert request.headers["authorization"] == f"Bearer {TOKEN}"
    assert request.headers["apikey"] == settings().publishable_key
    assert "service_role" not in request.headers["apikey"]
    assert [(item.workspace_id, item.role) for item in result] == [(WORKSPACE, "owner")]


def test_membership_repository_rejects_rows_for_a_different_subject() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json=[
                {
                    "user_id": "20000000-0000-4000-8000-000000000002",
                    "workspace_id": str(WORKSPACE),
                    "role": "owner",
                    "workspace": {"id": str(WORKSPACE), "name": "A primary"},
                }
            ],
        )

    repository = SupabaseWorkspaceRepository(
        settings(), transport=httpx.MockTransport(handler)
    )

    with pytest.raises(WorkspaceDataUnavailable):
        asyncio.run(
            repository.list_memberships(
                Principal(settings().jwt_issuer, SUBJECT), TOKEN
            )
        )
