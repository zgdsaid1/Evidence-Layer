"""Security tests for the fixed, app-owned synthetic fixture catalog."""

from dataclasses import replace
from datetime import datetime, timedelta, timezone
import os

import pytest

from evidence_layer.retrieval import synthetic_fixtures
from evidence_layer.retrieval.synthetic_fixtures import (
    SYNTHETIC_SOURCE_ID,
    SyntheticFixtureReadBoundary,
)
from evidence_layer.source_access import (
    SourceReadDenial,
    SourceReadDenialReason,
    SourceReadIntent,
    SourceRequestContext,
)


def _context(**changes):
    values = {
        "request_id": "fixture-request",
        "operation_id": "fixture-operation",
        "principal_id": "synthetic-development-principal",
        "tenant_id": "synthetic-development-tenant",
        "policy_version": "synthetic-catalog-v1",
        "expires_at": datetime.now(timezone.utc) + timedelta(minutes=5),
    }
    values.update(changes)
    return SourceRequestContext(**values)


def _intent(source_id=SYNTHETIC_SOURCE_ID, operation="retrieve", version=None):
    return SourceReadIntent(
        source_id=source_id,
        operation=operation,
        expected_version=version,
    )


def _track_opens(monkeypatch):
    calls = []
    original_open = os.open

    def tracked_open(path, flags, *args, **kwargs):
        calls.append((path, kwargs.get("dir_fd")))
        return original_open(path, flags, *args, **kwargs)

    monkeypatch.setattr(synthetic_fixtures.os, "open", tracked_open)
    return calls


def test_registered_synthetic_source_opens_fixed_fixture_and_returns_provenance(
    monkeypatch,
):
    calls = _track_opens(monkeypatch)
    boundary = SyntheticFixtureReadBoundary()
    readers = boundary.open_sources(
        _context(), (_intent(version="synthetic-fixture-v1"),)
    )

    assert not isinstance(readers, SourceReadDenial)
    assert len(readers) == 1
    assert len(calls) == 2
    assert calls[0] == (os.fspath(synthetic_fixtures._FIXTURE_DIRECTORY), None)
    assert calls[1][0] == synthetic_fixtures._FIXTURE_FILENAME
    assert calls[1][1] is not None
    reader = readers[0]
    records = list(reader.iter_records())
    reader.close()

    assert records
    assert all(record["source_id"] == SYNTHETIC_SOURCE_ID for record in records)
    assert all(
        str(record["source_url"]).startswith("https://example.test/synthetic/")
        for record in records
    )
    assert all(
        "synthetic" in str(record["text"]).casefold()
        or "btree" in str(record["text"]).casefold()
        for record in records
    )


@pytest.mark.parametrize(
    "intent",
    [
        _intent("unknown-source"),
        _intent("../../outside.jsonl"),
        _intent("/etc/passwd"),
        _intent(SYNTHETIC_SOURCE_ID, operation="index"),
        _intent(SYNTHETIC_SOURCE_ID, version="wrong-version"),
        SourceReadIntent(source_id=[], operation="retrieve"),
    ],
)
def test_invalid_or_out_of_scope_intent_is_denied_before_any_open(
    monkeypatch, intent
):
    calls = _track_opens(monkeypatch)
    result = SyntheticFixtureReadBoundary().open_sources(_context(), (intent,))

    assert isinstance(result, SourceReadDenial)
    assert calls == []


def test_unclassified_catalog_entry_is_denied_before_open(monkeypatch):
    calls = _track_opens(monkeypatch)
    entry = synthetic_fixtures._SYNTHETIC_SOURCE_CATALOG[SYNTHETIC_SOURCE_ID]
    monkeypatch.setattr(
        synthetic_fixtures,
        "_SYNTHETIC_SOURCE_CATALOG",
        {SYNTHETIC_SOURCE_ID: replace(entry, classification="protected")},
    )

    result = SyntheticFixtureReadBoundary().open_sources(_context(), (_intent(),))

    assert isinstance(result, SourceReadDenial)
    assert result.reason is SourceReadDenialReason.SCOPE_MISMATCH
    assert calls == []


def test_expired_catalog_source_is_denied_before_open(monkeypatch):
    calls = _track_opens(monkeypatch)
    entry = synthetic_fixtures._SYNTHETIC_SOURCE_CATALOG[SYNTHETIC_SOURCE_ID]
    expired = datetime.now(timezone.utc) - timedelta(seconds=1)
    monkeypatch.setattr(
        synthetic_fixtures,
        "_SYNTHETIC_SOURCE_CATALOG",
        {SYNTHETIC_SOURCE_ID: replace(entry, expires_at=expired)},
    )

    result = SyntheticFixtureReadBoundary().open_sources(_context(), (_intent(),))

    assert isinstance(result, SourceReadDenial)
    assert result.reason is SourceReadDenialReason.EXPIRED
    assert calls == []


def test_catalog_path_override_is_denied_before_open(monkeypatch):
    calls = _track_opens(monkeypatch)
    entry = synthetic_fixtures._SYNTHETIC_SOURCE_CATALOG[SYNTHETIC_SOURCE_ID]
    monkeypatch.setattr(
        synthetic_fixtures,
        "_SYNTHETIC_SOURCE_CATALOG",
        {SYNTHETIC_SOURCE_ID: replace(entry, filename="../../outside.jsonl")},
    )

    result = SyntheticFixtureReadBoundary().open_sources(_context(), (_intent(),))

    assert isinstance(result, SourceReadDenial)
    assert result.reason is SourceReadDenialReason.SCOPE_MISMATCH
    assert calls == []


def test_expired_request_context_is_denied_before_open(monkeypatch):
    calls = _track_opens(monkeypatch)
    expired = _context(expires_at=datetime.now(timezone.utc) - timedelta(seconds=1))

    result = SyntheticFixtureReadBoundary().open_sources(expired, (_intent(),))

    assert isinstance(result, SourceReadDenial)
    assert result.reason is SourceReadDenialReason.EXPIRED
    assert calls == []


def test_complete_intent_set_is_validated_before_first_open(monkeypatch):
    calls = _track_opens(monkeypatch)
    result = SyntheticFixtureReadBoundary().open_sources(
        _context(), (_intent(), _intent("not-registered"))
    )

    assert isinstance(result, SourceReadDenial)
    assert calls == []


def test_catalog_cannot_be_redirected_to_a_symlink(tmp_path, monkeypatch):
    outside = tmp_path / "synthetic-target.jsonl"
    outside.write_text(
        '{"passage_id":"x","source_id":"synthetic-development-notes-v1",'
        '"source_url":"https://example.test/synthetic/x","text":"synthetic"}\n',
        encoding="utf-8",
    )
    fixture_directory = tmp_path / "fixtures"
    fixture_directory.mkdir()
    (fixture_directory / "synthetic_evidence.jsonl").symlink_to(outside)
    monkeypatch.setattr(synthetic_fixtures, "_FIXTURE_DIRECTORY", fixture_directory)

    result = SyntheticFixtureReadBoundary().open_sources(_context(), (_intent(),))

    assert isinstance(result, SourceReadDenial)
    assert result.reason is SourceReadDenialReason.STORAGE_FAILURE
    assert str(outside) not in repr(result)


def test_symlinked_final_fixture_directory_is_rejected_without_opening_file(
    tmp_path, monkeypatch
):
    target_directory = tmp_path / "synthetic-target"
    target_directory.mkdir()
    (target_directory / "synthetic_evidence.jsonl").write_text(
        '{"passage_id":"synthetic-test","source_id":"synthetic-development-notes-v1",'
        '"source_url":"https://example.test/synthetic/test",'
        '"text":"synthetic test content"}\n',
        encoding="utf-8",
    )
    directory_link = tmp_path / "fixture-directory-link"
    directory_link.symlink_to(target_directory, target_is_directory=True)
    monkeypatch.setattr(synthetic_fixtures, "_FIXTURE_DIRECTORY", directory_link)
    calls = _track_opens(monkeypatch)

    result = SyntheticFixtureReadBoundary().open_sources(_context(), (_intent(),))

    assert isinstance(result, SourceReadDenial)
    assert result.reason is SourceReadDenialReason.STORAGE_FAILURE
    supports_safe_open = (
        getattr(os, "O_NOFOLLOW", None) is not None
        and getattr(os, "O_DIRECTORY", None) is not None
    )
    if not supports_safe_open:
        # Unsupported platforms must fail before attempting a potentially
        # following open; supported platforms must reject the directory link.
        assert calls == []
    else:
        assert calls == [(os.fspath(directory_link), None)]


def test_denial_details_do_not_disclose_source_or_path():
    denial = SyntheticFixtureReadBoundary().open_sources(
        _context(), (_intent("../../private/customer.jsonl"),)
    )

    assert isinstance(denial, SourceReadDenial)
    assert "private" not in repr(denial)
    assert "customer" not in repr(denial)
    assert "jsonl" not in repr(denial)
