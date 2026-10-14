"""Authorization value and lifecycle contract tests using test-only fakes."""

from __future__ import annotations

from dataclasses import fields, replace
from datetime import datetime, timedelta, timezone

import pytest

from evidence_layer.authorization import (
    DenyAllTransferAuthorizer,
    RequestOperationContext,
    TransferDenial,
    TransferDenialReason,
    TransferGrant,
    TransferIntent,
    grant_matches,
)


@pytest.fixture
def context() -> RequestOperationContext:
    return RequestOperationContext(
        request_id="request-1",
        operation_id="operation-1",
        principal_id="principal-1",
        tenant_id="tenant-1",
        policy_version="policy-v1",
    )


@pytest.fixture
def intent() -> TransferIntent:
    return TransferIntent(
        provider="jev",
        purpose="evidence_scoring",
        source_ids=frozenset({"source-a", "source-b"}),
        candidate_ids=frozenset({"candidate-a", "candidate-b"}),
        candidate_source_pairs=frozenset(
            {("candidate-a", "source-a"), ("candidate-b", "source-b")}
        ),
        data_categories=frozenset({"query_text", "candidate_text"}),
    )


def make_grant(context, intent, *, expires_at=None) -> TransferGrant:
    return TransferGrant(
        grant_id="grant-1",
        request_id=context.request_id,
        operation_id=context.operation_id,
        principal_id=context.principal_id,
        tenant_id=context.tenant_id,
        provider=intent.provider,
        purpose=intent.purpose,
        source_ids=intent.source_ids,
        candidate_ids=intent.candidate_ids,
        candidate_source_pairs=intent.candidate_source_pairs,
        data_categories=intent.data_categories,
        expires_at=expires_at
        or datetime.now(timezone.utc) + timedelta(minutes=1),
        policy_version=context.policy_version,
    )


class FakeOperationAuthorizer:
    """Test-only stateful fake; not a production provenance validator."""

    def __init__(self, grant: TransferGrant):
        self.grant = grant
        self.reserved_operation: tuple[str, str] | None = None
        self.used_candidates: set[str] = set()
        self.revoked = False

    def authorize(self, context, intent):
        if self.revoked or not grant_matches(context, intent, self.grant):
            return TransferDenial(TransferDenialReason.SCOPE_MISMATCH)
        return self.grant

    def reserve_operation(self, context, intent, grant):
        if self.revoked:
            return TransferDenial(TransferDenialReason.REVOKED)
        if not grant_matches(context, intent, grant):
            return TransferDenial(TransferDenialReason.SCOPE_MISMATCH)
        operation = (context.tenant_id, context.operation_id)
        if self.reserved_operation is not None:
            return TransferDenial(TransferDenialReason.REPLAYED)
        self.reserved_operation = operation
        return None

    def validate_candidate_use(
        self, context, intent, grant, candidate_id, *, now
    ):
        if self.revoked:
            return TransferDenial(TransferDenialReason.REVOKED)
        if not grant_matches(context, intent, grant, now=now):
            return TransferDenial(TransferDenialReason.EXPIRED)
        if self.reserved_operation != (context.tenant_id, context.operation_id):
            return TransferDenial(TransferDenialReason.REPLAYED)
        if candidate_id not in intent.candidate_ids:
            return TransferDenial(
                TransferDenialReason.CANDIDATE_NOT_IN_OPERATION
            )
        if candidate_id in self.used_candidates:
            return TransferDenial(TransferDenialReason.REPLAYED)
        self.used_candidates.add(candidate_id)
        return None

    def finish_operation(self, context, intent, grant):
        if self.reserved_operation != (context.tenant_id, context.operation_id):
            return TransferDenial(TransferDenialReason.REPLAYED)
        self.reserved_operation = None
        return None


def test_deny_all_authorizer_denies_each_operation_stage(context, intent):
    authorizer = DenyAllTransferAuthorizer()
    grant = make_grant(context, intent)

    assert authorizer.authorize(context, intent).reason is TransferDenialReason.DENY_ALL
    assert (
        authorizer.reserve_operation(context, intent, grant).reason
        is TransferDenialReason.DENY_ALL
    )
    assert (
        authorizer.validate_candidate_use(
            context, intent, grant, "candidate-a", now=datetime.now(timezone.utc)
        ).reason
        is TransferDenialReason.DENY_ALL
    )
    assert (
        authorizer.finish_operation(context, intent, grant).reason
        is TransferDenialReason.DENY_ALL
    )


def test_exact_context_and_complete_intent_scope_match(context, intent):
    grant = make_grant(context, intent)
    assert grant_matches(context, intent, grant)


@pytest.mark.parametrize(
    "context_change",
    [
        {"principal_id": "another-principal"},
        {"tenant_id": "another-tenant"},
        {"request_id": "another-request"},
        {"operation_id": "another-operation"},
        {"policy_version": "another-policy"},
    ],
)
def test_context_mismatch_denies(context, intent, context_change):
    assert not grant_matches(
        replace(context, **context_change), intent, make_grant(context, intent)
    )


@pytest.mark.parametrize(
    "intent_change",
    [
        {"provider": "openai_decisions"},
        {"purpose": "routing"},
        {"source_ids": frozenset({"source-a"})},
        {"candidate_ids": frozenset({"candidate-a"})},
        {
            "candidate_source_pairs": frozenset(
                {("candidate-a", "source-b"), ("candidate-b", "source-a")}
            )
        },
        {"data_categories": frozenset({"query_text"})},
    ],
)
def test_provider_purpose_or_scope_mismatch_denies(context, intent, intent_change):
    assert not grant_matches(
        context, replace(intent, **intent_change), make_grant(context, intent)
    )


def test_grant_field_mismatches_deny(context, intent):
    grant = make_grant(context, intent)
    for changes in (
        {"provider": "openai_decisions"},
        {"purpose": "routing"},
        {"tenant_id": "another-tenant"},
        {"request_id": "another-request"},
        {"operation_id": "another-operation"},
        {"data_categories": frozenset({"query_text"})},
        {"source_ids": frozenset({"source-a"})},
        {"candidate_ids": frozenset({"candidate-a"})},
    ):
        assert not grant_matches(context, intent, replace(grant, **changes))


def test_expired_or_naive_expiry_grants_deny(context, intent):
    expired = make_grant(
        context, intent, expires_at=datetime.now(timezone.utc) - timedelta(seconds=1)
    )
    naive = make_grant(
        context,
        intent,
        expires_at=datetime.now().replace(tzinfo=None) + timedelta(minutes=1),
    )

    assert not grant_matches(context, intent, expired)
    assert not grant_matches(context, intent, naive)


def test_operation_is_reserved_once_then_candidate_uses_are_individually_scoped(
    context, intent
):
    grant = make_grant(context, intent)
    fake = FakeOperationAuthorizer(grant)

    assert fake.reserve_operation(context, intent, grant) is None
    assert (
        fake.validate_candidate_use(
            context, intent, grant, "candidate-a", now=datetime.now(timezone.utc)
        )
        is None
    )
    assert (
        fake.validate_candidate_use(
            context, intent, grant, "candidate-b", now=datetime.now(timezone.utc)
        )
        is None
    )
    assert fake.reserve_operation(context, intent, grant).reason is TransferDenialReason.REPLAYED


def test_fake_denies_candidate_expansion_duplicate_replay_and_revocation(
    context, intent
):
    grant = make_grant(context, intent)
    fake = FakeOperationAuthorizer(grant)
    assert fake.reserve_operation(context, intent, grant) is None

    assert (
        fake.validate_candidate_use(
            context, intent, grant, "unauthorized", now=datetime.now(timezone.utc)
        ).reason
        is TransferDenialReason.CANDIDATE_NOT_IN_OPERATION
    )
    assert fake.validate_candidate_use(
        context, intent, grant, "candidate-a", now=datetime.now(timezone.utc)
    ) is None
    assert (
        fake.validate_candidate_use(
            context, intent, grant, "candidate-a", now=datetime.now(timezone.utc)
        ).reason
        is TransferDenialReason.REPLAYED
    )
    fake.revoked = True
    assert (
        fake.validate_candidate_use(
            context, intent, grant, "candidate-b", now=datetime.now(timezone.utc)
        ).reason
        is TransferDenialReason.REVOKED
    )


def test_denial_values_do_not_contain_query_candidate_or_credential_fields():
    denial = TransferDenial(
        TransferDenialReason.SCOPE_MISMATCH, audit_ref="audit-safe-123"
    )
    names = {field.name for field in fields(TransferDenial)}
    assert names == {"reason", "audit_ref"}
    assert "PRIVATE_QUERY" not in repr(denial)
    assert "PRIVATE_CANDIDATE" not in repr(denial)
    assert "API_SECRET" not in repr(denial)
