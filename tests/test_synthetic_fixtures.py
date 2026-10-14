"""Security tests for the fixed, app-owned synthetic fixture catalog."""

from dataclasses import replace
from datetime import datetime, timedelta, timezone
import os
import subprocess
import sys

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


def test_close_closes_suspended_iterator_and_prevents_more_reads():
    reader = SyntheticFixtureReadBoundary().open_sources(
        _context(), (_intent(),)
    )[0]
    iterator = reader.iter_records()
    first_record = next(iterator)
    stream = reader._stream
    assert first_record["source_id"] == SYNTHETIC_SOURCE_ID
    assert stream is not None and not stream.closed
    descriptor = stream.fileno()

    reader.close()

    assert stream.closed
    assert reader._stream is None
    with pytest.raises(OSError):
        os.fstat(descriptor)
    with pytest.raises(OSError, match="closed"):
        next(iterator)
    with pytest.raises(OSError, match="closed"):
        next(reader.iter_records())
    reader.close()


def test_iteration_closes_stream_at_end_and_after_read_exception(monkeypatch):
    reader = SyntheticFixtureReadBoundary().open_sources(
        _context(), (_intent(),)
    )[0]
    iterator = reader.iter_records()
    next(iterator)
    completed_stream = reader._stream
    assert completed_stream is not None
    completed_descriptor = completed_stream.fileno()

    list(iterator)

    assert completed_stream.closed
    assert reader._stream is None
    with pytest.raises(OSError):
        os.fstat(completed_descriptor)

    reader = SyntheticFixtureReadBoundary().open_sources(
        _context(), (_intent(),)
    )[0]
    iterator = reader.iter_records()
    next(iterator)
    failed_stream = reader._stream
    assert failed_stream is not None
    failed_descriptor = failed_stream.fileno()

    def fail_to_parse(_line):
        raise ValueError("synthetic parser failure")

    monkeypatch.setattr(synthetic_fixtures.json, "loads", fail_to_parse)
    with pytest.raises(ValueError, match="synthetic parser failure"):
        next(iterator)

    assert failed_stream.closed
    assert reader._stream is None
    with pytest.raises(OSError):
        os.fstat(failed_descriptor)


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


def test_missing_nonblocking_open_support_fails_closed_before_open(monkeypatch):
    calls = _track_opens(monkeypatch)
    monkeypatch.delattr(synthetic_fixtures.os, "O_NONBLOCK", raising=False)

    result = SyntheticFixtureReadBoundary().open_sources(_context(), (_intent(),))

    assert isinstance(result, SourceReadDenial)
    assert result.reason is SourceReadDenialReason.STORAGE_FAILURE
    assert calls == []


@pytest.mark.skipif(not hasattr(os, "mkfifo"), reason="FIFO creation is unavailable")
def test_fifo_fixture_is_rejected_without_blocking_or_lexical_fallback(tmp_path):
    fixture_directory = tmp_path / "fixtures"
    fixture_directory.mkdir()
    os.mkfifo(fixture_directory / "synthetic_evidence.jsonl")

    child = r"""
import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

from evidence_layer.retrieval import synthetic_fixtures
from evidence_layer.retrieval.local_corpus import LocalCorpusRetriever
from evidence_layer.source_access import (
    SourceReadDenialReason,
    SourceReadError,
    SourceRequestContext,
)

synthetic_fixtures._FIXTURE_DIRECTORY = Path(sys.argv[1])
retriever = LocalCorpusRetriever.for_synthetic_development_fixture()
def forbidden_fallback(*_args, **_kwargs):
    raise AssertionError("lexical fallback ran after source-read denial")
retriever._retrieve_candidates = forbidden_fallback
context = SourceRequestContext(
    request_id="fifo-request",
    operation_id="fifo-operation",
    principal_id="synthetic-test-principal",
    tenant_id="synthetic-test-tenant",
    policy_version="synthetic-fixture-policy-v1",
    expires_at=datetime.now(timezone.utc) + timedelta(minutes=1),
)
supports_safe_open = all(
    bool(getattr(os, flag, 0))
    for flag in ("O_NOFOLLOW", "O_DIRECTORY", "O_NONBLOCK")
)
expected = (
    SourceReadDenialReason.INVALID_SOURCE_DATA
    if supports_safe_open
    else SourceReadDenialReason.STORAGE_FAILURE
)
try:
    retriever.retrieve("synthetic FIFO query", request_context=context)
except SourceReadError as error:
    assert error.denial.reason is expected, error.denial.reason
else:
    raise AssertionError("FIFO source unexpectedly returned evidence")
print("bounded denial")
"""
    result = subprocess.run(
        [sys.executable, "-c", child, os.fspath(fixture_directory)],
        cwd=os.path.dirname(os.path.dirname(__file__)),
        env={
            **os.environ,
            "PYTHONPATH": os.pathsep.join(
                item
                for item in (
                    os.path.abspath(
                        os.path.join(os.path.dirname(__file__), os.pardir, "src")
                    ),
                    os.environ.get("PYTHONPATH"),
                )
                if item is not None
            ),
        },
        capture_output=True,
        text=True,
        timeout=5,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "bounded denial"


def test_denial_details_do_not_disclose_source_or_path():
    denial = SyntheticFixtureReadBoundary().open_sources(
        _context(), (_intent("../../private/customer.jsonl"),)
    )

    assert isinstance(denial, SourceReadDenial)
    assert "private" not in repr(denial)
    assert "customer" not in repr(denial)
    assert "jsonl" not in repr(denial)
