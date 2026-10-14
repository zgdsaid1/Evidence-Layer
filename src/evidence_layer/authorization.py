"""Framework-neutral types for provider data-transfer authorization.

These value objects describe a request; their Python type or construction does
not establish trusted provenance. A trusted host must build context from
server-side identity and source-authorization state. This phase provides no
grant issuer, and the default authorizer denies every transfer.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
from typing import Literal, Protocol

Provider = Literal["jev"]
TransferPurpose = Literal["evidence_scoring"]
DataCategory = Literal["query_text", "candidate_text"]


@dataclass(frozen=True)
class RequestOperationContext:
    """Identity and operation identifiers constructed by a future trusted host.

    Constructing this object from client-controlled fields does not make those
    fields trusted. It must not be deserialized directly from a client request.
    """

    request_id: str
    operation_id: str
    principal_id: str
    tenant_id: str
    policy_version: str


@dataclass(frozen=True)
class TransferIntent:
    """Non-content description of one exact provider-transfer operation.

    The sets describe the complete candidate batch. A future host must reserve
    the grant for this operation before the first candidate call, then validate
    each call against this same immutable scope.
    """

    provider: Provider
    purpose: TransferPurpose
    source_ids: frozenset[str]
    candidate_ids: frozenset[str]
    candidate_source_pairs: frozenset[tuple[str, str]]
    data_categories: frozenset[DataCategory]


class TransferDenialReason(str, Enum):
    DENY_ALL = "deny_all"
    MISSING_CONTEXT = "missing_context"
    SCOPE_MISMATCH = "scope_mismatch"
    EXPIRED = "expired"
    REVOKED = "revoked"
    REPLAYED = "replayed"
    CANDIDATE_NOT_IN_OPERATION = "candidate_not_in_operation"
    PHASE_DISABLED = "phase_disabled"


@dataclass(frozen=True)
class TransferGrant:
    """A grant's declared bindings; the object itself is not proof of trust.

    This is a value contract only. Phase 1 has no trusted issuer, signature,
    revocation store, replay store, or production grant validator.
    """

    grant_id: str
    request_id: str
    operation_id: str
    principal_id: str
    tenant_id: str
    provider: Provider
    purpose: TransferPurpose
    source_ids: frozenset[str]
    candidate_ids: frozenset[str]
    candidate_source_pairs: frozenset[tuple[str, str]]
    data_categories: frozenset[DataCategory]
    expires_at: datetime
    policy_version: str


@dataclass(frozen=True)
class TransferDenial:
    """Safe internal denial category and optional non-sensitive audit reference."""

    reason: TransferDenialReason
    audit_ref: str | None = None


TransferAuthorization = TransferGrant | TransferDenial


class TransferAuthorizer(Protocol):
    """Host-owned authorization port; implementations must validate provenance.

    ``authorize`` must validate expiry and revocation. ``reserve_operation``
    reserves/consumes a grant once for the full operation, not once per
    candidate. ``validate_candidate_use`` checks each intended call against
    that reserved operation without consuming it again. Implementations must
    make reservation, candidate use, and revocation checks atomic when used
    concurrently. A retry is another provider attempt and must be bounded and
    revalidated; SDK-hidden retries must be disabled or intercepted. Phase 1
    supplies no production implementation and no retry/replay store.
    """

    def authorize(
        self,
        context: RequestOperationContext,
        intent: TransferIntent,
    ) -> TransferAuthorization: ...

    def reserve_operation(
        self,
        context: RequestOperationContext,
        intent: TransferIntent,
        grant: TransferGrant,
    ) -> TransferDenial | None: ...

    def validate_candidate_use(
        self,
        context: RequestOperationContext,
        intent: TransferIntent,
        grant: TransferGrant,
        candidate_id: str,
        *,
        now: datetime,
    ) -> TransferDenial | None: ...

    def finish_operation(
        self,
        context: RequestOperationContext,
        intent: TransferIntent,
        grant: TransferGrant,
    ) -> TransferDenial | None: ...


class DenyAllTransferAuthorizer:
    """Safe default until a separately approved trusted host exists."""

    def authorize(
        self,
        context: RequestOperationContext,
        intent: TransferIntent,
    ) -> TransferDenial:
        return TransferDenial(TransferDenialReason.DENY_ALL)

    def reserve_operation(
        self,
        context: RequestOperationContext,
        intent: TransferIntent,
        grant: TransferGrant,
    ) -> TransferDenial:
        return TransferDenial(TransferDenialReason.DENY_ALL)

    def validate_candidate_use(
        self,
        context: RequestOperationContext,
        intent: TransferIntent,
        grant: TransferGrant,
        candidate_id: str,
        *,
        now: datetime,
    ) -> TransferDenial:
        return TransferDenial(TransferDenialReason.DENY_ALL)

    def finish_operation(
        self,
        context: RequestOperationContext,
        intent: TransferIntent,
        grant: TransferGrant,
    ) -> TransferDenial:
        return TransferDenial(TransferDenialReason.DENY_ALL)


def grant_matches(
    context: RequestOperationContext,
    intent: TransferIntent,
    grant: TransferGrant,
    *,
    now: datetime | None = None,
) -> bool:
    """Check declared bindings and expiry; does not establish grant provenance.

    Revocation, replay prevention, and atomic operation reservation require
    authorizer-owned state and are deliberately not simulated by this helper.
    """

    current = now or datetime.now(timezone.utc)
    expiry = grant.expires_at
    if expiry.tzinfo is None or current.tzinfo is None or expiry <= current:
        return False
    return (
        grant.request_id == context.request_id
        and grant.operation_id == context.operation_id
        and grant.principal_id == context.principal_id
        and grant.tenant_id == context.tenant_id
        and grant.policy_version == context.policy_version
        and grant.provider == intent.provider
        and grant.purpose == intent.purpose
        and grant.source_ids == intent.source_ids
        and grant.candidate_ids == intent.candidate_ids
        and grant.candidate_source_pairs == intent.candidate_source_pairs
        and grant.data_categories == intent.data_categories
    )
