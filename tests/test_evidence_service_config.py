from __future__ import annotations

import pytest

from evidence_service.config import ConfigurationError, SupabaseSettings


def valid_environment() -> dict[str, str]:
    return {
        "SUPABASE_URL": "https://project-ref.supabase.co",
        "SUPABASE_PUBLISHABLE_KEY": "sb_publishable_synthetic_test_key",
        "SUPABASE_JWT_ISSUER": "https://project-ref.supabase.co/auth/v1",
        "SUPABASE_JWT_AUDIENCE": "authenticated",
        "SUPABASE_JWT_ALGORITHMS": "ES256,RS256",
        "SUPABASE_JWKS_CACHE_TTL_SECONDS": "300",
    }


def test_settings_derive_trusted_jwks_and_rest_urls() -> None:
    configured = SupabaseSettings.from_environment(valid_environment())

    assert configured.jwks_url == (
        "https://project-ref.supabase.co/auth/v1/.well-known/jwks.json"
    )
    assert configured.rest_url == (
        "https://project-ref.supabase.co/rest/v1/workspace_memberships"
    )
    assert configured.jwt_algorithms == ("ES256", "RS256")


@pytest.mark.parametrize(
    "updates",
    [
        {"SUPABASE_URL": ""},
        {"SUPABASE_JWT_AUDIENCE": "anon"},
        {"SUPABASE_JWT_ALGORITHMS": "HS256"},
        {"SUPABASE_JWT_ALGORITHMS": "RS256,RS256"},
        {"SUPABASE_JWT_ALGORITHMS": ""},
        {"SUPABASE_JWKS_CACHE_TTL_SECONDS": "301"},
        {"SUPABASE_URL": "http://example.supabase.co"},
        {"SUPABASE_JWT_ISSUER": "https://project-ref.supabase.co/other"},
        {"SUPABASE_JWT_ISSUER": "https://another-project.supabase.co/auth/v1"},
        {"SUPABASE_PUBLISHABLE_KEY": "sb_secret_synthetic_key"},
        {"SUPABASE_PUBLISHABLE_KEY": "legacy-anon-jwt"},
    ],
)
def test_unsafe_or_incomplete_settings_fail_closed(updates: dict[str, str]) -> None:
    environment = valid_environment()
    environment.update(updates)

    with pytest.raises(ConfigurationError):
        SupabaseSettings.from_environment(environment)
