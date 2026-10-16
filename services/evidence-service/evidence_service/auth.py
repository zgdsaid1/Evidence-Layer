"""Cryptographic verification of Supabase Auth access tokens."""

from __future__ import annotations

import asyncio
import time
import uuid
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Protocol

import httpx
import jwt

from evidence_service.config import SupabaseSettings

JWT_LEEWAY_SECONDS = 30
JWKS_UNKNOWN_KID_REFRESH_COOLDOWN_SECONDS = 1.0


class AuthenticationRejected(Exception):
    """The supplied token is not a valid Supabase user access token."""


class AuthenticationUnavailable(Exception):
    """The trusted verification-key source cannot currently be checked."""


@dataclass(frozen=True)
class Principal:
    issuer: str
    subject: uuid.UUID


@dataclass(frozen=True, repr=False)
class AuthenticatedRequest:
    principal: Principal
    access_token: str = field(repr=False)


class TokenVerifier(Protocol):
    async def verify(self, token: str) -> Principal: ...


class SupabaseTokenVerifier:
    """Verifies only configured asymmetric Supabase Auth signing keys."""

    def __init__(
        self,
        settings: SupabaseSettings,
        *,
        transport: httpx.AsyncBaseTransport | None = None,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._settings = settings
        self._transport = transport
        self._clock = clock
        self._keys: dict[str, tuple[str, object]] = {}
        self._expires_at = 0.0
        self._last_refresh_at: float | None = None
        self._last_refresh_failed = False
        self._lock = asyncio.Lock()

    async def verify(self, token: str) -> Principal:
        try:
            header = jwt.get_unverified_header(token)
        except (jwt.PyJWTError, TypeError, ValueError) as exc:
            raise AuthenticationRejected from exc

        algorithm = header.get("alg")
        kid = header.get("kid")
        if (
            header.get("typ") != "JWT"
            or not isinstance(kid, str)
            or not kid
            or algorithm not in self._settings.jwt_algorithms
        ):
            raise AuthenticationRejected

        key = await self._key_for(kid, algorithm)
        try:
            claims = jwt.decode(
                token,
                key,
                algorithms=[algorithm],
                audience=self._settings.jwt_audience,
                issuer=self._settings.jwt_issuer,
                leeway=JWT_LEEWAY_SECONDS,
                options={
                    "require": ["aud", "exp", "iat", "iss", "sub", "role"],
                    "verify_signature": True,
                    "verify_exp": True,
                    "verify_iat": True,
                    "verify_nbf": True,
                },
            )
        except (jwt.PyJWTError, TypeError, ValueError) as exc:
            raise AuthenticationRejected from exc

        if claims.get("role") != "authenticated" or claims.get("is_anonymous") is not False:
            raise AuthenticationRejected
        try:
            subject = uuid.UUID(claims["sub"])
        except (KeyError, TypeError, ValueError, AttributeError) as exc:
            raise AuthenticationRejected from exc

        return Principal(issuer=claims["iss"], subject=subject)

    async def _key_for(self, kid: str, algorithm: str) -> object:
        now = self._clock()
        if now < self._expires_at and kid in self._keys:
            key_algorithm, key = self._keys[kid]
            if key_algorithm != algorithm:
                raise AuthenticationRejected
            return key

        async with self._lock:
            now = self._clock()
            if now < self._expires_at and kid in self._keys:
                key_algorithm, key = self._keys[kid]
                if key_algorithm != algorithm:
                    raise AuthenticationRejected
                return key

            if (
                self._last_refresh_at is not None
                and now - self._last_refresh_at
                < JWKS_UNKNOWN_KID_REFRESH_COOLDOWN_SECONDS
            ):
                if now >= self._expires_at or self._last_refresh_failed:
                    raise AuthenticationUnavailable
                raise AuthenticationRejected

            await self._refresh_keys()
            key_entry = self._keys.get(kid)
            if key_entry is None:
                raise AuthenticationRejected
            key_algorithm, key = key_entry
            if key_algorithm != algorithm:
                raise AuthenticationRejected
            return key

    async def _refresh_keys(self) -> None:
        self._last_refresh_at = self._clock()
        try:
            async with httpx.AsyncClient(
                timeout=self._settings.timeout_seconds,
                transport=self._transport,
            ) as client:
                response = await client.get(self._settings.jwks_url)
                response.raise_for_status()
                document = response.json()

            if not isinstance(document, dict) or not isinstance(document.get("keys"), list):
                raise AuthenticationUnavailable

            refreshed: dict[str, tuple[str, object]] = {}
            for item in document["keys"]:
                if not isinstance(item, dict):
                    raise AuthenticationUnavailable
                kid = item.get("kid")
                algorithm = item.get("alg")
                if not isinstance(kid, str) or not kid:
                    continue
                if algorithm not in self._settings.jwt_algorithms:
                    continue
                if item.get("use", "sig") != "sig":
                    continue
                key_ops = item.get("key_ops")
                if key_ops is not None:
                    if not isinstance(key_ops, list) or any(
                        not isinstance(operation, str) for operation in key_ops
                    ):
                        raise AuthenticationUnavailable
                    if "verify" not in key_ops:
                        continue
                if kid in refreshed:
                    raise AuthenticationUnavailable
                try:
                    signing_key = jwt.PyJWK.from_dict(item, algorithm=algorithm).key
                except (jwt.PyJWTError, TypeError, ValueError) as exc:
                    raise AuthenticationUnavailable from exc
                refreshed[kid] = (algorithm, signing_key)

            if not refreshed:
                raise AuthenticationUnavailable
            self._keys = refreshed
            self._expires_at = self._clock() + self._settings.jwks_cache_ttl_seconds
            self._last_refresh_failed = False
        except (httpx.HTTPError, ValueError, TypeError) as exc:
            self._last_refresh_failed = True
            raise AuthenticationUnavailable from exc
        except AuthenticationUnavailable:
            self._last_refresh_failed = True
            raise
