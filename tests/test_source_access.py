"""Default-deny source-read contract tests; no production trust is implied."""

from datetime import datetime, timedelta, timezone

from evidence_layer.source_access import (
    DenyAllSourceReadBoundary,
    SourceReadDenialReason,
    SourceReadIntent,
    SourceRequestContext,
    context_is_expired,
)


def _context(*, expires_at=None):
    return SourceRequestContext(
        request_id="request-test",
        operation_id="operation-test",
        principal_id="principal-test",
        tenant_id="tenant-test",
        policy_version="policy-test",
        expires_at=expires_at or datetime.now(timezone.utc) + timedelta(minutes=1),
    )


def test_default_boundary_denies_content_reads():
    result = DenyAllSourceReadBoundary().open_sources(
        _context(),
        (SourceReadIntent(source_id="source-test", operation="retrieve"),),
    )
    assert result.reason is SourceReadDenialReason.DENY_ALL


def test_default_boundary_denies_empty_source_scope():
    result = DenyAllSourceReadBoundary().open_sources(_context(), ())
    assert result.reason is SourceReadDenialReason.UNKNOWN_SOURCE


def test_context_expiry_is_checked_without_claiming_provenance():
    expired = _context(
        expires_at=datetime.now(timezone.utc) - timedelta(seconds=1)
    )
    assert context_is_expired(expired)


def test_intent_binds_source_operation_and_optional_version():
    intent = SourceReadIntent(
        source_id="source-test",
        operation="retrieve",
        expected_version="version-test",
    )
    assert intent.source_id == "source-test"
    assert intent.operation == "retrieve"
    assert intent.expected_version == "version-test"
