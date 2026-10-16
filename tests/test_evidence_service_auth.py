from __future__ import annotations

import time
import uuid

import httpx
import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import ec, rsa
from fastapi.testclient import TestClient
from jwt.utils import to_base64url_uint

from evidence_service.app import create_app
from evidence_service.auth import (
    AuthenticatedRequest,
    AuthenticationRejected,
    Principal,
    SupabaseTokenVerifier,
)
from evidence_service.config import SupabaseSettings
from evidence_service.tenant_context import WorkspaceMembership

ISSUER = "https://project-ref.supabase.co/auth/v1"
SUBJECT_A = uuid.UUID("10000000-0000-4000-8000-000000000001")
SUBJECT_B = uuid.UUID("20000000-0000-4000-8000-000000000002")
WORKSPACE_A = uuid.UUID("a1000000-0000-4000-8000-000000000001")
WORKSPACE_B = uuid.UUID("b3000000-0000-4000-8000-000000000003")


def settings() -> SupabaseSettings:
    return SupabaseSettings(
        supabase_url="https://project-ref.supabase.co",
        publishable_key="sb_publishable_synthetic_test_key",
        jwt_issuer=ISSUER,
        jwt_audience="authenticated",
        jwt_algorithms=("RS256",),
    )


def new_signing_key() -> rsa.RSAPrivateKey:
    return rsa.generate_private_key(public_exponent=65537, key_size=2048)


def jwk_for(key: rsa.RSAPrivateKey, kid: str) -> dict[str, object]:
    public = key.public_key().public_numbers()
    return {
        "kty": "RSA",
        "use": "sig",
        "key_ops": ["verify"],
        "alg": "RS256",
        "kid": kid,
        "n": to_base64url_uint(public.n).decode("ascii"),
        "e": to_base64url_uint(public.e).decode("ascii"),
    }


def token_for(
    key: rsa.RSAPrivateKey,
    *,
    kid: str = "key-1",
    subject: uuid.UUID = SUBJECT_A,
    claim_overrides: dict[str, object] | None = None,
    header_overrides: dict[str, object] | None = None,
) -> str:
    now = int(time.time())
    claims: dict[str, object] = {
        "iss": ISSUER,
        "aud": "authenticated",
        "sub": str(subject),
        "role": "authenticated",
        "is_anonymous": False,
        "session_id": "30000000-0000-4000-8000-000000000003",
        "iat": now,
        "exp": now + 300,
    }
    claims.update(claim_overrides or {})
    headers: dict[str, object] = {"kid": kid, "typ": "JWT"}
    headers.update(header_overrides or {})
    return jwt.encode(claims, key, algorithm="RS256", headers=headers)


class JwksFeed:
    def __init__(
        self,
        documents: list[dict[str, object]] | None = None,
        *,
        status_code: int = 200,
    ) -> None:
        self.documents = documents or []
        self.status_code = status_code
        self.calls = 0

    def __call__(self, request: httpx.Request) -> httpx.Response:
        assert request.url == httpx.URL(settings().jwks_url)
        self.calls += 1
        if self.status_code != 200:
            return httpx.Response(self.status_code, json={"error": "synthetic"})
        document = self.documents[min(self.calls - 1, len(self.documents) - 1)]
        return httpx.Response(200, json=document)


class DirectorySpy:
    def __init__(self) -> None:
        self.calls: list[tuple[str, uuid.UUID, str]] = []

    async def list_memberships(
        self, principal: Principal, access_token: str
    ) -> list[WorkspaceMembership]:
        self.calls.append(("list", principal.subject, access_token))
        if principal.subject == SUBJECT_A:
            return [WorkspaceMembership(WORKSPACE_A, "A primary", "owner")]
        return []

    async def get_membership(
        self,
        principal: Principal,
        access_token: str,
        workspace_id: uuid.UUID,
    ) -> WorkspaceMembership | None:
        self.calls.append((str(workspace_id), principal.subject, access_token))
        if principal.subject == SUBJECT_A and workspace_id == WORKSPACE_A:
            return WorkspaceMembership(WORKSPACE_A, "A primary", "owner")
        return None


def make_client(
    feed: JwksFeed,
    directory: DirectorySpy,
) -> TestClient:
    verifier = SupabaseTokenVerifier(
        settings(), transport=httpx.MockTransport(feed)
    )
    return TestClient(
        create_app(
            settings(),
            token_verifier=verifier,
            workspace_directory=directory,
        )
    )


def response_for_claims(
    claim_overrides: dict[str, object],
    *,
    signing_key: rsa.RSAPrivateKey,
    directory: DirectorySpy,
    header_overrides: dict[str, object] | None = None,
) -> httpx.Response:
    feed = JwksFeed([{"keys": [jwk_for(signing_key, "key-1")]}])
    token = token_for(
        signing_key,
        claim_overrides=claim_overrides,
        header_overrides=header_overrides,
    )
    with make_client(feed, directory) as client:
        return client.get("/v1/me", headers={"Authorization": f"Bearer {token}"})


def test_valid_access_token_returns_verified_subject_and_memberships() -> None:
    key = new_signing_key()
    directory = DirectorySpy()
    feed = JwksFeed([{"keys": [jwk_for(key, "key-1")]}])
    token = token_for(key)

    with make_client(feed, directory) as client:
        response = client.get("/v1/me", headers={"Authorization": f"Bearer {token}"})

    assert response.status_code == 200
    assert response.json() == {
        "user_id": str(SUBJECT_A),
        "issuer": ISSUER,
        "workspaces": [{"id": str(WORKSPACE_A), "name": "A primary", "role": "owner"}],
    }
    assert directory.calls == [("list", SUBJECT_A, token)]
    assert token not in repr(AuthenticatedRequest(Principal(ISSUER, SUBJECT_A), token))


def test_missing_and_malformed_tokens_are_rejected_before_directory_access() -> None:
    key = new_signing_key()
    directory = DirectorySpy()
    feed = JwksFeed([{"keys": [jwk_for(key, "key-1")]}])

    with make_client(feed, directory) as client:
        missing = client.get("/v1/me")
        malformed = client.get(
            "/v1/me", headers={"Authorization": "Bearer not-a-jwt"}
        )
        non_bearer = client.get(
            "/v1/me", headers={"Authorization": "Basic aW52YWxpZA=="}
        )

    assert [missing.status_code, malformed.status_code, non_bearer.status_code] == [401, 401, 401]
    assert directory.calls == []
    assert feed.calls == 0


@pytest.mark.parametrize(
    "claims",
    [
        {"exp": int(time.time()) - 120},
        {"iss": "https://attacker.example/auth/v1"},
        {"aud": "anon"},
        {"iat": int(time.time()) + 300},
        {"exp": None},
        {"iat": None},
        {"role": "service_role"},
        {"role": "anon"},
        {"is_anonymous": True},
        {"nbf": int(time.time()) + 300},
        {"sub": "not-a-uuid"},
    ],
)
def test_invalid_claims_are_rejected_before_directory_access(
    claims: dict[str, object],
) -> None:
    key = new_signing_key()
    directory = DirectorySpy()

    response = response_for_claims(
        claims, signing_key=key, directory=directory
    )

    assert response.status_code == 401
    assert response.json() == {"detail": "Invalid bearer access token"}
    assert directory.calls == []


def test_non_jwt_token_type_is_rejected() -> None:
    key = new_signing_key()
    directory = DirectorySpy()
    response = response_for_claims(
        {},
        signing_key=key,
        directory=directory,
        header_overrides={"typ": "at+jwt"},
    )
    assert response.status_code == 401
    assert directory.calls == []


def test_unconfigured_symmetric_algorithm_is_rejected_without_jwks_fetch() -> None:
    directory = DirectorySpy()
    feed = JwksFeed([{"keys": []}])
    token = jwt.encode(
        {
            "iss": ISSUER,
            "aud": "authenticated",
            "sub": str(SUBJECT_A),
            "role": "authenticated",
            "is_anonymous": False,
            "iat": int(time.time()),
            "exp": int(time.time()) + 300,
        },
        "synthetic-only-secret-for-test-with-more-than-32-bytes",
        algorithm="HS256",
        headers={"kid": "symmetric-key", "typ": "JWT"},
    )

    with make_client(feed, directory) as client:
        response = client.get("/v1/me", headers={"Authorization": f"Bearer {token}"})

    assert response.status_code == 401
    assert feed.calls == 0
    assert directory.calls == []


def test_bad_signature_is_rejected_before_directory_access() -> None:
    trusted_key = new_signing_key()
    attacker_key = new_signing_key()
    directory = DirectorySpy()
    feed = JwksFeed([{"keys": [jwk_for(trusted_key, "key-1")]}])
    token = token_for(attacker_key, kid="key-1")

    with make_client(feed, directory) as client:
        response = client.get("/v1/me", headers={"Authorization": f"Bearer {token}"})

    assert response.status_code == 401
    assert directory.calls == []


def test_unknown_kid_is_rejected_after_jwks_refresh() -> None:
    trusted_key = new_signing_key()
    other_key = new_signing_key()
    directory = DirectorySpy()
    feed = JwksFeed([{"keys": [jwk_for(trusted_key, "key-1")]}])
    token = token_for(other_key, kid="unknown-key")

    with make_client(feed, directory) as client:
        response = client.get("/v1/me", headers={"Authorization": f"Bearer {token}"})

    assert response.status_code == 401
    assert feed.calls == 1
    assert directory.calls == []


def test_jwks_outage_fails_closed_without_directory_access() -> None:
    key = new_signing_key()
    directory = DirectorySpy()
    feed = JwksFeed(status_code=503)
    token = token_for(key)

    with make_client(feed, directory) as client:
        response = client.get("/v1/me", headers={"Authorization": f"Bearer {token}"})

    assert response.status_code == 503
    assert directory.calls == []


def test_new_kid_forces_jwks_refresh_and_accepts_rotated_key() -> None:
    old_key = new_signing_key()
    rotated_key = new_signing_key()
    directory = DirectorySpy()
    feed = JwksFeed(
        [
            {"keys": [jwk_for(old_key, "old-key")]},
            {"keys": [jwk_for(old_key, "old-key"), jwk_for(rotated_key, "new-key")]},
        ]
    )
    now = [0.0]
    verifier = SupabaseTokenVerifier(
        settings(),
        transport=httpx.MockTransport(feed),
        clock=lambda: now[0],
    )
    old_token = token_for(old_key, kid="old-key")
    new_token = token_for(rotated_key, kid="new-key")

    import asyncio

    async def verify_both() -> tuple[Principal, Principal]:
        before = await verifier.verify(old_token)
        now[0] = 2.0
        after = await verifier.verify(new_token)
        return before, after

    assert asyncio.run(verify_both()) == (
        Principal(ISSUER, SUBJECT_A),
        Principal(ISSUER, SUBJECT_A),
    )
    assert feed.calls == 2


def test_unknown_kid_refresh_is_cooled_down_to_avoid_repeated_fetches() -> None:
    key = new_signing_key()
    feed = JwksFeed([{"keys": [jwk_for(key, "trusted-key")]}])
    now = [10.0]
    verifier = SupabaseTokenVerifier(
        settings(),
        transport=httpx.MockTransport(feed),
        clock=lambda: now[0],
    )

    import asyncio

    async def reject_unknowns() -> None:
        for kid in ("unknown-one", "unknown-two"):
            with pytest.raises(AuthenticationRejected):
                await verifier.verify(token_for(key, kid=kid))

    asyncio.run(reject_unknowns())
    assert feed.calls == 1


def test_workspace_selection_requires_membership_for_verified_user() -> None:
    key = new_signing_key()
    directory = DirectorySpy()
    feed = JwksFeed([{"keys": [jwk_for(key, "key-1")]}])
    token = token_for(key)

    with make_client(feed, directory) as client:
        allowed = client.get(
            f"/v1/workspaces/{WORKSPACE_A}",
            headers={"Authorization": f"Bearer {token}"},
        )
        denied = client.get(
            f"/v1/workspaces/{WORKSPACE_B}",
            headers={"Authorization": f"Bearer {token}"},
        )

    assert allowed.status_code == 200
    assert allowed.json() == {
        "id": str(WORKSPACE_A),
        "name": "A primary",
        "role": "owner",
    }
    assert denied.status_code == 404
    assert [call[0] for call in directory.calls] == [str(WORKSPACE_A), str(WORKSPACE_B)]


def test_rotated_key_document_replaces_old_key_after_cache_expiry() -> None:
    old_key = new_signing_key()
    new_key = new_signing_key()
    feed = JwksFeed(
        [
            {"keys": [jwk_for(old_key, "old-key")]},
            {"keys": [jwk_for(new_key, "new-key")]},
        ]
    )
    now = [0.0]
    verifier = SupabaseTokenVerifier(
        settings(),
        transport=httpx.MockTransport(feed),
        clock=lambda: now[0],
    )
    old_token = token_for(old_key, kid="old-key")
    new_token = token_for(new_key, kid="new-key")

    import asyncio

    async def verify_across_rotation() -> tuple[Principal, Principal]:
        before = await verifier.verify(old_token)
        now[0] = 301.0
        after = await verifier.verify(new_token)
        return before, after

    assert asyncio.run(verify_across_rotation()) == (
        Principal(ISSUER, SUBJECT_A),
        Principal(ISSUER, SUBJECT_A),
    )
    assert feed.calls == 2


def test_es256_supabase_signing_key_is_cryptographically_verified() -> None:
    private_key = ec.generate_private_key(ec.SECP256R1())
    public = private_key.public_key().public_numbers()
    jwk = {
        "kty": "EC",
        "use": "sig",
        "key_ops": ["verify"],
        "alg": "ES256",
        "kid": "ec-key",
        "crv": "P-256",
        "x": to_base64url_uint(public.x).decode("ascii"),
        "y": to_base64url_uint(public.y).decode("ascii"),
    }
    claims = {
        "iss": ISSUER,
        "aud": "authenticated",
        "sub": str(SUBJECT_A),
        "role": "authenticated",
        "is_anonymous": False,
        "iat": int(time.time()),
        "exp": int(time.time()) + 300,
    }
    token = jwt.encode(
        claims,
        private_key,
        algorithm="ES256",
        headers={"kid": "ec-key", "typ": "JWT"},
    )
    configured = SupabaseSettings(
        supabase_url="https://project-ref.supabase.co",
        publishable_key="sb_publishable_synthetic_test_key",
        jwt_issuer=ISSUER,
        jwt_audience="authenticated",
        jwt_algorithms=("ES256",),
    )
    verifier = SupabaseTokenVerifier(
        configured,
        transport=httpx.MockTransport(JwksFeed([{"keys": [jwk]}])),
    )

    import asyncio

    assert asyncio.run(verifier.verify(token)) == Principal(ISSUER, SUBJECT_A)
