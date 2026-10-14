"""Tests for LocalCorpusRetriever with explicitly unprotected file fixtures."""

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from evidence_layer.retrieval import LocalCorpusRetriever
from evidence_layer.schemas import EvidenceCandidate
from evidence_layer.scoring.lexical import LexicalScorer
from evidence_layer.selection import select_top_k
from evidence_layer.source_access import (
    DenyAllSourceReadBoundary,
    SourceReadDenial,
    SourceReadDenialReason,
    SourceReadIntent,
    SourceReadLease,
    SourceRequestContext,
)

RECORDS = {
    "src/1": [
        {
            "passage_id": "p_index",
            "source_id": "src/1",
            "source_url": "https://example.test/index",
            "section": "1 Indexes",
            "text": "btree index speeds lookups",
        },
        {
            "passage_id": "p_index_long",
            "source_id": "src/1",
            "source_url": "https://example.test/index-long",
            "section": "1.1 Index details",
            "text": "btree index " + "the " * 20 + "btree index",
        },
    ],
    "src/2": [
        {
            "passage_id": "p_vacuum",
            "source_id": "src/2",
            "source_url": "https://example.test/vacuum",
            "text": "vacuum reclaims dead storage",
        }
    ],
}


class _FixtureReader:
    def __init__(self, lease: SourceReadLease, path: Path, boundary):
        self.lease = lease
        self.path = path
        self.boundary = boundary

    def iter_records(self):
        self.boundary.content_reads.append(self.lease.source_id)
        for line in self.path.read_text(encoding="utf-8").splitlines():
            if line.strip():
                yield json.loads(line)

    def close(self):
        return None


class _UnprotectedFixtureBoundary:
    """Test-only fixture boundary; not a trusted runtime authorizer."""

    def __init__(
        self,
        files,
        context,
        *,
        classifications,
        lease_expiry=None,
        lease_overrides=None,
    ):
        self.files = files
        self.context = context
        self.classifications = classifications
        self.lease_expiry = lease_expiry
        self.lease_overrides = lease_overrides or {}
        self.open_requests = []
        self.content_reads = []

    def open_sources(self, context, intents):
        intents = tuple(intents)
        self.open_requests.append((context, intents))
        if context is None or context != self.context:
            return SourceReadDenial(SourceReadDenialReason.SCOPE_MISMATCH)
        if context.expires_at <= datetime.now(timezone.utc):
            return SourceReadDenial(SourceReadDenialReason.EXPIRED)
        if not intents:
            return SourceReadDenial(SourceReadDenialReason.UNKNOWN_SOURCE)
        # Authorize and classify every source before returning any reader.
        for intent in intents:
            if (
                intent.operation != "retrieve"
                or intent.source_id not in self.files
                or self.classifications.get(intent.source_id)
                != "unprotected-development"
                or (
                    intent.expected_version is not None
                    and intent.expected_version != "fixture-v1"
                )
            ):
                return SourceReadDenial(SourceReadDenialReason.SCOPE_MISMATCH)
        expiry = self.lease_expiry or context.expires_at
        readers = []
        for intent in intents:
            lease_values = {
                "request_id": context.request_id,
                "operation_id": context.operation_id,
                "principal_id": context.principal_id,
                "tenant_id": context.tenant_id,
                "source_id": intent.source_id,
                "operation": intent.operation,
                "source_version": "fixture-v1",
                "expires_at": expiry,
            }
            lease_values.update(self.lease_overrides)
            readers.append(
                _FixtureReader(
                    SourceReadLease(**lease_values),
                    self.files[intent.source_id],
                    self,
                )
            )
        return tuple(readers)


def _context(**changes):
    values = {
        "request_id": "request-1",
        "operation_id": "operation-1",
        "principal_id": "test-principal",
        "tenant_id": "test-tenant",
        "policy_version": "fixture-policy-v1",
        "expires_at": datetime.now(timezone.utc) + timedelta(minutes=5),
    }
    values.update(changes)
    return SourceRequestContext(**values)


@pytest.fixture
def retrieval_setup(tmp_path, monkeypatch):
    files = {}
    for source_id, records in RECORDS.items():
        path = tmp_path / f"{source_id.replace('/', '-')}.jsonl"
        path.write_text(
            "\n".join(json.dumps(record) for record in records) + "\n",
            encoding="utf-8",
        )
        files[source_id] = path
    context = _context()
    boundary = _UnprotectedFixtureBoundary(
        files,
        context,
        classifications={source_id: "unprotected-development" for source_id in files},
    )
    def fixture_open_sources(_deny_all, context, intents):
        return boundary.open_sources(context, intents)

    monkeypatch.setattr(
        DenyAllSourceReadBoundary, "open_sources", fixture_open_sources
    )
    retriever = LocalCorpusRetriever(tuple(files))
    return retriever, context, boundary


def _retrieve(setup, query, **kwargs):
    retriever, context, _ = setup
    return retriever.retrieve(query, request_context=context, **kwargs)


def test_relevant_query_returns_ranked_evidence(retrieval_setup):
    result = _retrieve(retrieval_setup, "btree index lookups", top_k=5, budget_words=500)
    assert result.status == "ok"
    ids = [e.evidence_id for e in result.evidence]
    assert "p_vacuum" not in ids
    scores = [e.score for e in result.evidence]
    assert scores == sorted(scores, reverse=True)
    assert ids[0] == "p_index"


def test_no_match_returns_no_results(retrieval_setup):
    result = _retrieve(retrieval_setup, "zebra giraffe")
    assert result.status == "no_results"
    assert result.evidence == []


@pytest.mark.parametrize("query", ["", "   ", "\n\t"])
def test_empty_query_rejected(retrieval_setup, query):
    retriever, _, boundary = retrieval_setup
    with pytest.raises(ValueError, match="query"):
        retriever.retrieve(query)
    assert boundary.content_reads == []


@pytest.mark.parametrize("top_k", [0, -1, True, 1.5])
def test_invalid_top_k_rejected(retrieval_setup, top_k):
    retriever, context, boundary = retrieval_setup
    with pytest.raises((ValueError, TypeError), match="top_k"):
        retriever.retrieve("index", request_context=context, top_k=top_k)
    assert boundary.content_reads == []


@pytest.mark.parametrize("budget", [0, -5, True, 2.0])
def test_invalid_budget_rejected(retrieval_setup, budget):
    retriever, context, boundary = retrieval_setup
    with pytest.raises((ValueError, TypeError), match="budget_words"):
        retriever.retrieve("index", request_context=context, budget_words=budget)
    assert boundary.content_reads == []


def test_top_k_is_respected(retrieval_setup):
    result = _retrieve(retrieval_setup, "btree index lookups", top_k=1)
    assert len(result.evidence) == 1


def test_budget_words_is_respected(retrieval_setup):
    result = _retrieve(retrieval_setup, "btree index lookups", budget_words=10)
    assert sum(len(e.text.split()) for e in result.evidence) <= 10
    assert result.used_words == sum(len(e.text.split()) for e in result.evidence)


def test_large_candidate_does_not_block_smaller_later_one(retrieval_setup):
    full = _retrieve(retrieval_setup, "btree index", top_k=5, budget_words=500)
    assert full.evidence[0].evidence_id == "p_index_long"
    small = _retrieve(retrieval_setup, "btree index", top_k=5, budget_words=10)
    assert [e.evidence_id for e in small.evidence] == ["p_index"]
    assert small.status == "ok"


def test_evidence_id_and_citation_come_from_source_record(retrieval_setup):
    result = _retrieve(retrieval_setup, "btree index lookups")
    by_id = {record["passage_id"]: record for rows in RECORDS.values() for record in rows}
    for evidence in result.evidence:
        source = by_id[evidence.evidence_id]
        assert (evidence.source_id, evidence.source_url, evidence.text) == (
            source["source_id"], source["source_url"], source["text"]
        )
        assert evidence.section == source.get("section")
    vac = _retrieve(retrieval_setup, "vacuum").evidence[0]
    assert vac.section is None


def test_tiny_budget_returns_budget_exhausted(retrieval_setup):
    result = _retrieve(retrieval_setup, "btree index lookups", budget_words=1)
    assert result.status == "budget_exhausted"
    assert result.evidence == []
    assert result.candidate_count > 0


def test_lexical_scorer_and_select_top_k_unchanged():
    scorer = LexicalScorer()
    assert scorer.score("integer range", "integer range") == pytest.approx(1.0)
    assert scorer.score("integer", "banana") == 0.0
    cands = [
        EvidenceCandidate(candidate_id=i, source_id="s", source_url="u", text=t)
        for i, t in (("b", "integer range"), ("a", "integer range"), ("c", "banana"))
    ]
    assert select_top_k(cands, scorer, "integer range", 2) == ["a", "b"]


def test_construction_performs_zero_content_reads(retrieval_setup, monkeypatch):
    retriever, _, boundary = retrieval_setup
    boundary.content_reads.clear()
    original_read_text = Path.read_text

    def tracked_read_text(path, *args, **kwargs):
        boundary.content_reads.append("opened")
        return original_read_text(path, *args, **kwargs)

    monkeypatch.setattr(Path, "open", tracked_read_text)
    monkeypatch.setattr(Path, "read_text", tracked_read_text)
    LocalCorpusRetriever(("src/1",))
    assert boundary.content_reads == []
    assert retriever is not None


def test_caller_supplied_storage_path_is_not_a_source_scope(tmp_path):
    path = tmp_path / "unclassified.jsonl"
    path.write_text("SECRET CONTENT MUST NOT BE READ\n", encoding="utf-8")
    with pytest.raises(TypeError, match="source_ids"):
        LocalCorpusRetriever(path)


def test_caller_injected_boundary_cannot_enable_runtime_reads():
    class AllowEverything:
        def open_sources(self, context, intents):
            raise AssertionError("caller-supplied boundaries are unsupported")

    with pytest.raises(TypeError, match="source_read_boundary"):
        LocalCorpusRetriever(
            ("source",), source_read_boundary=AllowEverything()
        )


def test_missing_or_expired_context_denies_before_content_read(retrieval_setup):
    retriever, _, boundary = retrieval_setup
    from evidence_layer.source_access import SourceReadError

    with pytest.raises(SourceReadError) as missing:
        retriever.retrieve("btree index")
    assert missing.value.denial.reason is SourceReadDenialReason.MISSING_CONTEXT

    expired = _context(expires_at=datetime.now(timezone.utc) - timedelta(seconds=1))
    with pytest.raises(SourceReadError) as expired_error:
        retriever.retrieve("btree index", request_context=expired)
    assert expired_error.value.denial.reason is SourceReadDenialReason.EXPIRED
    assert boundary.content_reads == []


def test_denied_or_mismatched_source_scope_never_opens_content(retrieval_setup):
    retriever, context, boundary = retrieval_setup
    from evidence_layer.source_access import SourceReadError

    boundary.classifications["src/2"] = "protected"
    with pytest.raises(SourceReadError) as denied:
        retriever.retrieve("btree", request_context=context)
    assert denied.value.denial.reason is SourceReadDenialReason.SCOPE_MISMATCH
    assert boundary.content_reads == []

    boundary.classifications["src/2"] = "unprotected-development"
    mismatched = _context(tenant_id="another-tenant")
    with pytest.raises(SourceReadError) as mismatch:
        retriever.retrieve("btree", request_context=mismatched)
    assert mismatch.value.denial.reason is SourceReadDenialReason.SCOPE_MISMATCH
    assert boundary.content_reads == []

    unlisted_source = LocalCorpusRetriever(
        ("unlisted-source",)
    )
    with pytest.raises(SourceReadError) as unknown:
        unlisted_source.retrieve("btree", request_context=context)
    assert unknown.value.denial.reason is SourceReadDenialReason.SCOPE_MISMATCH
    assert boundary.content_reads == []

    traversal_source = LocalCorpusRetriever(("../../private/file.jsonl",))
    with pytest.raises(SourceReadError):
        traversal_source.retrieve("btree", request_context=context)
    assert boundary.content_reads == []


def test_wrong_operation_or_source_version_is_denied_before_open(retrieval_setup):
    _, context, boundary = retrieval_setup
    wrong_operation = boundary.open_sources(
        context, (SourceReadIntent("src/1", "index"),)
    )
    wrong_version = boundary.open_sources(
        context,
        (SourceReadIntent("src/1", "retrieve", expected_version="stale"),),
    )
    assert isinstance(wrong_operation, SourceReadDenial)
    assert wrong_operation.reason is SourceReadDenialReason.SCOPE_MISMATCH
    assert isinstance(wrong_version, SourceReadDenial)
    assert wrong_version.reason is SourceReadDenialReason.SCOPE_MISMATCH
    assert boundary.content_reads == []


def test_expired_reader_lease_denies_before_iterating(retrieval_setup):
    retriever, context, boundary = retrieval_setup
    boundary.lease_expiry = datetime.now(timezone.utc) - timedelta(seconds=1)
    from evidence_layer.source_access import SourceReadError

    with pytest.raises(SourceReadError) as expired:
        retriever.retrieve("btree", request_context=context)
    assert expired.value.denial.reason is SourceReadDenialReason.EXPIRED
    assert boundary.content_reads == []


@pytest.mark.parametrize(
    "lease_override",
    [
        {"operation_id": "another-operation"},
        {"tenant_id": "another-tenant"},
        {"source_id": "another-source"},
        {"request_id": "another-request"},
    ],
)
def test_reader_lease_scope_mismatch_denies_before_iterating(
    tmp_path, monkeypatch, lease_override
):
    fixture = tmp_path / "one-source.jsonl"
    fixture.write_text(
        json.dumps(RECORDS["src/1"][0]) + "\n", encoding="utf-8"
    )
    context = _context()
    boundary = _UnprotectedFixtureBoundary(
        {"src/1": fixture},
        context,
        classifications={"src/1": "unprotected-development"},
        lease_overrides=lease_override,
    )

    def fixture_open_sources(_deny_all, received_context, intents):
        return boundary.open_sources(received_context, intents)

    monkeypatch.setattr(
        DenyAllSourceReadBoundary, "open_sources", fixture_open_sources
    )
    retriever = LocalCorpusRetriever(("src/1",))
    from evidence_layer.source_access import SourceReadError

    with pytest.raises(SourceReadError) as mismatch:
        retriever.retrieve("btree", request_context=context)
    assert mismatch.value.denial.reason is SourceReadDenialReason.SCOPE_MISMATCH
    assert boundary.content_reads == []


def test_scope_denial_hides_content_paths_and_storage_exception_details(retrieval_setup):
    retriever, context, boundary = retrieval_setup
    boundary.classifications["src/2"] = "protected"
    from evidence_layer.source_access import SourceReadError

    with pytest.raises(SourceReadError) as error:
        retriever.retrieve("SECRET_CONTENT", request_context=context)
    rendered = str(error.value)
    assert "SECRET_CONTENT" not in rendered
    assert str(next(iter(boundary.files.values()))) not in rendered
    assert "protected" not in rendered
    assert boundary.content_reads == []


def test_storage_exception_details_are_suppressed(retrieval_setup):
    retriever, context, boundary = retrieval_setup
    secret_path = boundary.files["src/1"].with_name("private-storage-path.jsonl")
    boundary.files["src/1"] = secret_path
    from evidence_layer.source_access import SourceReadError

    with pytest.raises(SourceReadError) as error:
        retriever.retrieve("btree", request_context=context)
    assert error.value.denial.reason is SourceReadDenialReason.STORAGE_FAILURE
    assert str(secret_path) not in str(error.value)
    assert "No such file" not in str(error.value)


def test_fixture_reads_only_after_all_sources_are_classified(retrieval_setup):
    retriever, context, boundary = retrieval_setup
    result = retriever.retrieve("btree", request_context=context)
    assert result.status == "ok"
    assert set(boundary.content_reads) == {"src/1", "src/2"}
    assert len(boundary.open_requests) == 1


def test_default_source_denial_stops_before_scoring_or_returning_evidence(
    monkeypatch,
):
    from evidence_layer.source_access import SourceReadError

    retriever = LocalCorpusRetriever(("unclassified-source",))
    context = _context()
    content_opens = []
    ranking_calls = []

    def record_open(*args, **kwargs):
        content_opens.append(True)
        raise AssertionError("content must not be opened after source denial")

    def record_rank(*args, **kwargs):
        ranking_calls.append(True)
        raise AssertionError("ranking must not run after source denial")

    monkeypatch.setattr(Path, "open", record_open)
    monkeypatch.setattr(Path, "read_text", record_open)
    monkeypatch.setattr(LocalCorpusRetriever, "_rank", record_rank)

    with pytest.raises(SourceReadError):
        retriever.retrieve("synthetic query", request_context=context)

    assert content_opens == []
    assert ranking_calls == []
