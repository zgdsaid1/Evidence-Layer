"""Default-deny contracts for reading source content.

These types describe a request; their Python type or construction does not
establish trusted identity or authorization. A trusted host must validate
request provenance, resolve source ownership and policy, and own the storage
operation. Phase 1 provides no production host, source catalog, ACL, or
production allowing boundary. The default boundary denies every content read;
the sole opt-in exception is a fixed, unprotected synthetic development fixture.

An allowing implementation must authorize the complete source scope before it
opens any source, bind returned readers to one request/operation/source version,
and never accept a storage path from the caller. Test fakes are not production
authorization evidence.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
from typing import Literal, Protocol

SourceReadOperation = Literal["retrieve", "index", "refresh"]


@dataclass(frozen=True)
class SourceRequestContext:
    """Request identity claims that a trusted host must validate.

    Never deserialize this value directly from client fields. These fields are
    bindings for an authorization decision, not proof that the claims are true.
    """

    request_id: str
    operation_id: str
    principal_id: str
    tenant_id: str
    policy_version: str
    expires_at: datetime


@dataclass(frozen=True)
class SourceReadIntent:
    """One source-level content operation, without a storage locator."""

    source_id: str
    operation: SourceReadOperation
    expected_version: str | None = None


class SourceReadDenialReason(str, Enum):
    DENY_ALL = "deny_all"
    MISSING_CONTEXT = "missing_context"
    EXPIRED = "expired"
    SCOPE_MISMATCH = "scope_mismatch"
    UNKNOWN_SOURCE = "unknown_source"
    REVOKED = "revoked"
    REPLAYED = "replayed"
    STORAGE_FAILURE = "storage_failure"
    INVALID_SOURCE_DATA = "invalid_source_data"


@dataclass(frozen=True)
class SourceReadDenial:
    """Bounded denial information; never contains content or storage details."""

    reason: SourceReadDenialReason


@dataclass(frozen=True)
class SourceReadLease:
    """Declared scope for a reader returned by a trusted boundary.

    Matching these fields catches accidental scope drift. The dataclass itself
    does not prove provenance; only the trusted boundary can establish that.
    """

    request_id: str
    operation_id: str
    principal_id: str
    tenant_id: str
    source_id: str
    operation: SourceReadOperation
    source_version: str
    expires_at: datetime


class AuthorizedSourceReader(Protocol):
    """Bounded reader returned only after a boundary authorizes and opens it."""

    @property
    def lease(self) -> SourceReadLease: ...

    def iter_records(self) -> Iterable[Mapping[str, object]]: ...

    def close(self) -> None: ...


SourceReadResult = tuple[AuthorizedSourceReader, ...] | SourceReadDenial


class SourceReadBoundary(Protocol):
    """Host-owned authorize-and-open operation.

    Implementations must validate context provenance, expiry, revocation, and
    every intent before opening any content. They then open only the authorized,
    version-pinned sources. A denial for any intent must result in no content
    open for the operation. Authorization and opening must be coordinated
    against the same source version. Phase 1 has no production implementation
    of these guarantees or durable replay/concurrency controls. The fixed
    synthetic fixture exception does not validate trusted identity or authorize
    real sources.
    """

    def open_sources(
        self,
        context: SourceRequestContext,
        intents: Sequence[SourceReadIntent],
    ) -> SourceReadResult: ...


class DenyAllSourceReadBoundary:
    """Safe runtime default while no trusted source host exists."""

    def open_sources(
        self,
        context: SourceRequestContext,
        intents: Sequence[SourceReadIntent],
    ) -> SourceReadDenial:
        if not intents:
            return SourceReadDenial(SourceReadDenialReason.UNKNOWN_SOURCE)
        return SourceReadDenial(SourceReadDenialReason.DENY_ALL)


class SourceReadError(Exception):
    """Safe retrieval denial that does not reveal content, paths, or causes."""

    def __init__(self, denial: SourceReadDenial):
        reason = (
            denial.reason
            if isinstance(denial.reason, SourceReadDenialReason)
            else SourceReadDenialReason.SCOPE_MISMATCH
        )
        self.denial = SourceReadDenial(reason)
        super().__init__("Source content is unavailable.")


def context_is_expired(
    context: SourceRequestContext, *, now: datetime | None = None
) -> bool:
    """Check a context's declared expiry; this does not validate its provenance."""

    current = now or datetime.now(timezone.utc)
    return (
        context.expires_at.tzinfo is None
        or current.tzinfo is None
        or context.expires_at <= current
    )
