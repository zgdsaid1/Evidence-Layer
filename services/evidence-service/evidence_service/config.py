"""Explicit, fail-closed settings for a single Supabase Auth project."""

from __future__ import annotations

import ipaddress
import os
from collections.abc import Mapping
from dataclasses import dataclass
from urllib.parse import urlsplit


class ConfigurationError(ValueError):
    """Raised when identity configuration is absent or unsafe."""


SUPPORTED_JWT_ALGORITHMS = frozenset({"ES256", "RS256"})


def _is_loopback(hostname: str | None) -> bool:
    if hostname == "localhost":
        return True
    try:
        return ipaddress.ip_address(hostname or "").is_loopback
    except ValueError:
        return False


def _validate_service_url(value: str, *, name: str, allow_path: bool) -> None:
    try:
        parsed = urlsplit(value)
        parsed.port
    except ValueError as exc:
        raise ConfigurationError(f"{name} is not a valid service URL") from exc
    if (
        parsed.scheme != "https" and not (parsed.scheme == "http" and _is_loopback(parsed.hostname))
    ):
        raise ConfigurationError(f"{name} must use HTTPS (HTTP is allowed only on loopback)")
    if not parsed.hostname or parsed.username or parsed.password or parsed.query or parsed.fragment:
        raise ConfigurationError(f"{name} is not a valid service URL")
    if not allow_path and parsed.path not in {"", "/"}:
        raise ConfigurationError(f"{name} must not include a path")


@dataclass(frozen=True)
class SupabaseSettings:
    supabase_url: str
    publishable_key: str
    jwt_issuer: str
    jwt_audience: str
    jwt_algorithms: tuple[str, ...]
    jwks_cache_ttl_seconds: int = 300
    timeout_seconds: float = 3.0

    @property
    def jwks_url(self) -> str:
        return f"{self.jwt_issuer.rstrip('/')}/.well-known/jwks.json"

    @property
    def rest_url(self) -> str:
        return f"{self.supabase_url.rstrip('/')}/rest/v1/workspace_memberships"

    @classmethod
    def from_environment(
        cls, environment: Mapping[str, str] | None = None
    ) -> SupabaseSettings:
        values = os.environ if environment is None else environment
        required = (
            "SUPABASE_URL",
            "SUPABASE_PUBLISHABLE_KEY",
            "SUPABASE_JWT_ISSUER",
            "SUPABASE_JWT_AUDIENCE",
            "SUPABASE_JWT_ALGORITHMS",
        )
        missing = [name for name in required if not values.get(name, "").strip()]
        if missing:
            raise ConfigurationError("Required Supabase settings are missing")

        supabase_url = values["SUPABASE_URL"].strip().rstrip("/")
        issuer = values["SUPABASE_JWT_ISSUER"].strip().rstrip("/")
        _validate_service_url(supabase_url, name="SUPABASE_URL", allow_path=False)
        _validate_service_url(issuer, name="SUPABASE_JWT_ISSUER", allow_path=True)
        parsed_url = urlsplit(supabase_url)
        parsed_issuer = urlsplit(issuer)
        if parsed_issuer.path.rstrip("/") != "/auth/v1":
            raise ConfigurationError("SUPABASE_JWT_ISSUER must identify the Auth v1 issuer")
        if (parsed_url.scheme, parsed_url.hostname, parsed_url.port) != (
            parsed_issuer.scheme,
            parsed_issuer.hostname,
            parsed_issuer.port,
        ):
            raise ConfigurationError("Supabase API URL and Auth issuer must use the same project origin")

        publishable_key = values["SUPABASE_PUBLISHABLE_KEY"].strip()
        if not publishable_key.startswith("sb_publishable_") or len(publishable_key) <= len(
            "sb_publishable_"
        ):
            raise ConfigurationError("Only a Supabase publishable API key is supported")

        audience = values["SUPABASE_JWT_AUDIENCE"].strip()
        if audience != "authenticated":
            raise ConfigurationError("SUPABASE_JWT_AUDIENCE must be authenticated")

        algorithms = tuple(
            item.strip()
            for item in values["SUPABASE_JWT_ALGORITHMS"].split(",")
            if item.strip()
        )
        if (
            not algorithms
            or len(set(algorithms)) != len(algorithms)
            or not set(algorithms).issubset(SUPPORTED_JWT_ALGORITHMS)
        ):
            raise ConfigurationError("Only configured ES256 and RS256 signing keys are supported")

        try:
            cache_ttl = int(values.get("SUPABASE_JWKS_CACHE_TTL_SECONDS", "300"))
        except ValueError as exc:
            raise ConfigurationError("JWKS cache duration must be an integer") from exc
        if not 1 <= cache_ttl <= 300:
            raise ConfigurationError("JWKS cache duration must be between 1 and 300 seconds")

        return cls(
            supabase_url=supabase_url,
            publishable_key=publishable_key,
            jwt_issuer=issuer,
            jwt_audience=audience,
            jwt_algorithms=algorithms,
            jwks_cache_ttl_seconds=cache_ttl,
        )
