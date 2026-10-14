"""Retrieval behavior against the application's single synthetic fixture."""

from dataclasses import replace
from datetime import datetime, timedelta, timezone

import pytest

from evidence_layer.retrieval import LocalCorpusRetriever
from evidence_layer.schemas import EvidenceCandidate
from evidence_layer.scoring.lexical import LexicalScorer
from evidence_layer.selection import select_top_k
from evidence_layer.source_access import (
    DenyAllSourceReadBoundary,
    SourceReadDenial,
    SourceReadDenialReason,
    SourceReadError,
    SourceReadIntent,
    SourceReadLease,
    SourceRequestContext,
)

from evidence_layer.retrieval.synthetic_fixtures import SYNTHETIC_SOURCE_ID


def _context(**changes):
    values = {
        "request_id": "request-1",
        "operation_id": "operation-1",
        "principal_id": "synthetic-test-principal",
        "tenant_id": "synthetic-test-tenant",
        "policy_version": "synthetic-fixture-policy-v1",
        "expires_at": datetime.now(timezone.utc) + timedelta(minutes=5),
    }
    values.update(changes)
    return SourceRequestContext(**values)


@pytest.fixture
def retrieval_setup():
    # Explicit opt-in to one built-in unprotected fixture. This context is test
    # metadata, not proof of trusted identity or authorization for real data.
    return LocalCorpusRetriever.for_synthetic_development_fixture(), _context()


def _retrieve(setup, query, **kwargs):
    retriever, context = setup
    return retriever.retrieve(query, request_context=context, **kwargs)


class _ContractTestReader:
    """Test-only reader for validating the retriever's lease checks."""

    def __init__(self, lease, *, error=None):
        self.lease = lease
        self.error = error
        self.iterations = 0
        self.close_calls = 0

    def iter_records(self):
        self.iterations += 1
        if self.error is not None:
            raise self.error
        yield {
            "passage_id": "synthetic-contract-passage",
            "source_id": self.lease.source_id,
            "source_url": "https://example.test/synthetic/contract",
            "text": "synthetic contract fixture",
        }

    def close(self):
        self.close_calls += 1


class _ContractTestBoundary:
    """Fake boundary used only to exercise retriever validation contracts."""

    def __init__(self, result=None, *, error=None):
        self.result = result
        self.error = error
        self.calls = []

    def open_sources(self, context, intents):
        self.calls.append((context, tuple(intents)))
        if self.error is not None:
            raise self.error
        return self.result


class _MultiSourcePreflightBoundary:
    """Fake operation boundary that classifies the whole scope before opening."""

    def __init__(self, denied_source_id):
        self.denied_source_id = denied_source_id
        self.received_intents = ()
        self.preflighted_source_ids = []
        self.readers_created = 0

    def open_sources(self, _context, intents):
        self.received_intents = tuple(intents)
        for intent in self.received_intents:
            self.preflighted_source_ids.append(intent.source_id)
            if intent.source_id == self.denied_source_id:
                return SourceReadDenial(SourceReadDenialReason.SCOPE_MISMATCH)
        self.readers_created = len(self.received_intents)
        return SourceReadDenial(SourceReadDenialReason.DENY_ALL)


def _bind_contract_test_boundary(monkeypatch, boundary):
    # Keep the public constructor's denial behavior intact. This private test
    # seam replaces only the built-in deny-all method for a single test.
    def open_sources(_default_boundary, context, intents):
        return boundary.open_sources(context, intents)

    monkeypatch.setattr(DenyAllSourceReadBoundary, "open_sources", open_sources)


def _lease(context, source_id="source-1", **changes):
    values = {
        "request_id": context.request_id,
        "operation_id": context.operation_id,
        "principal_id": context.principal_id,
        "tenant_id": context.tenant_id,
        "source_id": source_id,
        "operation": "retrieve",
        "source_version": "synthetic-contract-v1",
        "expires_at": datetime.now(timezone.utc) + timedelta(minutes=5),
    }
    values.update(changes)
    return SourceReadLease(**values)


def test_synthetic_query_returns_ranked_evidence_with_fixture_provenance(
    retrieval_setup,
):
    result = _retrieve(
        retrieval_setup, "btree index lookup", top_k=5, budget_words=500
    )

    assert result.status == "ok"
    assert result.scoring_provider == "lexical"
    assert [item.evidence_id for item in result.evidence][0] == "synthetic-index-long"
    assert all(item.source_id == SYNTHETIC_SOURCE_ID for item in result.evidence)
    assert all("example.test/synthetic/" in item.source_url for item in result.evidence)
    assert all(item.text for item in result.evidence)


def test_no_match_returns_no_results(retrieval_setup):
    result = _retrieve(retrieval_setup, "zebra giraffe")
    assert result.status == "no_results"
    assert result.evidence == []


@pytest.mark.parametrize("query", ["", "   ", "\n\t"])
def test_empty_query_is_rejected_before_open(retrieval_setup, monkeypatch, query):
    retriever, context = retrieval_setup
    from evidence_layer.retrieval import synthetic_fixtures

    opens = []
    monkeypatch.setattr(synthetic_fixtures.os, "open", lambda *a, **k: opens.append(a))
    with pytest.raises(ValueError, match="query"):
        retriever.retrieve(query, request_context=context)
    assert opens == []


@pytest.mark.parametrize("top_k", [0, -1, True, 1.5])
def test_invalid_top_k_is_rejected_before_open(retrieval_setup, monkeypatch, top_k):
    retriever, context = retrieval_setup
    from evidence_layer.retrieval import synthetic_fixtures

    opens = []
    monkeypatch.setattr(synthetic_fixtures.os, "open", lambda *a, **k: opens.append(a))
    with pytest.raises((ValueError, TypeError), match="top_k"):
        retriever.retrieve("index", request_context=context, top_k=top_k)
    assert opens == []


@pytest.mark.parametrize("budget", [0, -5, True, 2.0])
def test_invalid_budget_is_rejected_before_open(retrieval_setup, monkeypatch, budget):
    retriever, context = retrieval_setup
    from evidence_layer.retrieval import synthetic_fixtures

    opens = []
    monkeypatch.setattr(synthetic_fixtures.os, "open", lambda *a, **k: opens.append(a))
    with pytest.raises((ValueError, TypeError), match="budget_words"):
        retriever.retrieve("index", request_context=context, budget_words=budget)
    assert opens == []


def test_top_k_is_respected(retrieval_setup):
    result = _retrieve(retrieval_setup, "btree index lookup", top_k=1)
    assert len(result.evidence) == 1


def test_word_budget_is_respected(retrieval_setup):
    result = _retrieve(retrieval_setup, "btree index", budget_words=10)
    assert sum(len(item.text.split()) for item in result.evidence) <= 10
    assert result.used_words == sum(len(item.text.split()) for item in result.evidence)


def test_large_candidate_does_not_block_smaller_later_one(retrieval_setup):
    full = _retrieve(retrieval_setup, "btree index", top_k=5, budget_words=500)
    assert full.evidence[0].evidence_id == "synthetic-index-long"
    small = _retrieve(retrieval_setup, "btree index", top_k=5, budget_words=10)
    assert [item.evidence_id for item in small.evidence] == ["synthetic-index"]
    assert small.status == "ok"


def test_evidence_citations_are_taken_from_the_registered_fixture(retrieval_setup):
    result = _retrieve(retrieval_setup, "vacuum")
    assert len(result.evidence) == 1
    evidence = result.evidence[0]
    assert evidence.evidence_id == "synthetic-vacuum"
    assert evidence.source_id == SYNTHETIC_SOURCE_ID
    assert evidence.source_url == "https://example.test/synthetic/vacuum"
    assert evidence.section is None
    assert evidence.text == "A synthetic vacuum example reclaims test storage."


def test_tiny_budget_returns_budget_exhausted(retrieval_setup):
    result = _retrieve(retrieval_setup, "btree index lookup", budget_words=1)
    assert result.status == "budget_exhausted"
    assert result.evidence == []
    assert result.candidate_count > 0


def test_lexical_scorer_and_select_top_k_unchanged():
    scorer = LexicalScorer()
    assert scorer.score("integer range", "integer range") == pytest.approx(1.0)
    assert scorer.score("integer", "banana") == 0.0
    candidates = [
        EvidenceCandidate(candidate_id=i, source_id="s", source_url="u", text=t)
        for i, t in (("b", "integer range"), ("a", "integer range"), ("c", "banana"))
    ]
    assert select_top_k(candidates, scorer, "integer range", 2) == ["a", "b"]


def test_construction_performs_zero_content_opens(monkeypatch):
    from evidence_layer.retrieval import synthetic_fixtures

    opens = []
    monkeypatch.setattr(synthetic_fixtures.os, "open", lambda *a, **k: opens.append(a))
    LocalCorpusRetriever((SYNTHETIC_SOURCE_ID,))
    LocalCorpusRetriever.for_synthetic_development_fixture()
    assert opens == []


def test_caller_supplied_storage_path_is_not_a_source_scope(tmp_path):
    path = tmp_path / "unclassified.jsonl"
    path.write_text("SYNTHETIC CONTENT MUST NOT BE READ\n", encoding="utf-8")
    with pytest.raises(TypeError, match="source_ids"):
        LocalCorpusRetriever(path)


def test_caller_injected_boundary_cannot_enable_runtime_reads():
    class AllowEverything:
        def open_sources(self, context, intents):
            raise AssertionError("caller-supplied boundaries are unsupported")

    with pytest.raises(TypeError, match="source_read_boundary"):
        LocalCorpusRetriever(
            (SYNTHETIC_SOURCE_ID,), source_read_boundary=AllowEverything()
        )


def test_missing_or_expired_context_denies_before_open(retrieval_setup, monkeypatch):
    retriever, _ = retrieval_setup
    from evidence_layer.retrieval import synthetic_fixtures

    opens = []
    monkeypatch.setattr(synthetic_fixtures.os, "open", lambda *a, **k: opens.append(a))
    with pytest.raises(SourceReadError) as missing:
        retriever.retrieve("btree index")
    assert missing.value.denial.reason is SourceReadDenialReason.MISSING_CONTEXT

    expired = _context(expires_at=datetime.now(timezone.utc) - timedelta(seconds=1))
    with pytest.raises(SourceReadError) as expired_error:
        retriever.retrieve("btree index", request_context=expired)
    assert expired_error.value.denial.reason is SourceReadDenialReason.EXPIRED
    assert opens == []


def test_default_boundary_denial_stops_before_open_ranking_or_evidence(monkeypatch):
    from evidence_layer.retrieval import synthetic_fixtures

    retriever = LocalCorpusRetriever(("unclassified-synthetic-source",))
    content_opens = []
    ranking_calls = []

    def record_open(*args, **kwargs):
        content_opens.append(args)
        raise AssertionError("content must not be opened after source denial")

    def record_rank(*args, **kwargs):
        ranking_calls.append(True)
        raise AssertionError("ranking must not run after source denial")

    monkeypatch.setattr(synthetic_fixtures.os, "open", record_open)
    monkeypatch.setattr(LocalCorpusRetriever, "_rank", record_rank)
    with pytest.raises(SourceReadError):
        retriever.retrieve("synthetic query", request_context=_context())

    assert content_opens == []
    assert ranking_calls == []


def test_source_read_denial_does_not_fall_back_to_lexical_content(monkeypatch):
    from evidence_layer.retrieval import synthetic_fixtures

    retriever = LocalCorpusRetriever((SYNTHETIC_SOURCE_ID,))
    monkeypatch.setattr(
        synthetic_fixtures.os,
        "open",
        lambda *a, **k: (_ for _ in ()).throw(AssertionError("unexpected open")),
    )
    monkeypatch.setattr(
        LocalCorpusRetriever,
        "_retrieve_candidates",
        lambda *a, **k: (_ for _ in ()).throw(
            AssertionError("fallback is forbidden")
        ),
    )
    with pytest.raises(SourceReadError):
        retriever.retrieve("btree", request_context=_context())


@pytest.mark.parametrize(
    "lease_changes",
    [
        {"request_id": "another-request"},
        {"operation_id": "another-operation"},
        {"principal_id": "another-principal"},
        {"tenant_id": "another-tenant"},
        {"source_id": "another-source"},
        {"operation": "index"},
    ],
)
def test_mismatched_reader_lease_is_rejected_before_iteration(
    monkeypatch, lease_changes
):
    context = _context()
    reader = _ContractTestReader(_lease(context, **lease_changes))
    boundary = _ContractTestBoundary((reader,))
    _bind_contract_test_boundary(monkeypatch, boundary)
    retriever = LocalCorpusRetriever(("source-1",))

    with pytest.raises(SourceReadError) as error:
        retriever.retrieve("synthetic query", request_context=context)

    assert error.value.denial.reason is SourceReadDenialReason.SCOPE_MISMATCH
    assert reader.iterations == 0
    assert reader.close_calls == 1


def test_expired_reader_lease_is_rejected_before_iteration(monkeypatch):
    context = _context()
    expired = datetime.now(timezone.utc) - timedelta(seconds=1)
    reader = _ContractTestReader(_lease(context, expires_at=expired))
    boundary = _ContractTestBoundary((reader,))
    _bind_contract_test_boundary(monkeypatch, boundary)
    retriever = LocalCorpusRetriever(("source-1",))

    with pytest.raises(SourceReadError) as error:
        retriever.retrieve("synthetic query", request_context=context)

    assert error.value.denial.reason is SourceReadDenialReason.EXPIRED
    assert reader.iterations == 0
    assert reader.close_calls == 1


def test_multiple_sources_are_preflighted_as_one_operation(monkeypatch):
    context = _context()
    boundary = _MultiSourcePreflightBoundary(denied_source_id="source-2")
    _bind_contract_test_boundary(monkeypatch, boundary)
    retriever = LocalCorpusRetriever(("source-1", "source-2"))
    ranking_calls = []
    monkeypatch.setattr(
        LocalCorpusRetriever,
        "_rank",
        lambda *args, **kwargs: ranking_calls.append(True),
    )

    with pytest.raises(SourceReadError) as error:
        retriever.retrieve("synthetic query", request_context=context)

    assert error.value.denial.reason is SourceReadDenialReason.SCOPE_MISMATCH
    assert boundary.received_intents == (
        SourceReadIntent("source-1", "retrieve"),
        SourceReadIntent("source-2", "retrieve"),
    )
    assert boundary.preflighted_source_ids == ["source-1", "source-2"]
    assert boundary.readers_created == 0
    assert ranking_calls == []


def test_boundary_exception_is_sanitized(monkeypatch):
    context = _context()
    boundary = _ContractTestBoundary(
        error=RuntimeError("private path /srv/customer/records SECRET-CONTENT")
    )
    _bind_contract_test_boundary(monkeypatch, boundary)
    retriever = LocalCorpusRetriever(("source-1",))

    with pytest.raises(SourceReadError) as error:
        retriever.retrieve("synthetic query", request_context=context)

    assert error.value.denial.reason is SourceReadDenialReason.STORAGE_FAILURE
    assert str(error.value) == "Source content is unavailable."
    assert "private path" not in str(error.value)
    assert "SECRET-CONTENT" not in str(error.value)


def test_reader_exception_is_sanitized_and_reader_is_closed(monkeypatch):
    context = _context()
    reader = _ContractTestReader(
        _lease(context),
        error=RuntimeError("private path /srv/customer/records SECRET-CONTENT"),
    )
    boundary = _ContractTestBoundary((reader,))
    _bind_contract_test_boundary(monkeypatch, boundary)
    retriever = LocalCorpusRetriever(("source-1",))

    with pytest.raises(SourceReadError) as error:
        retriever.retrieve("synthetic query", request_context=context)

    assert error.value.denial.reason is SourceReadDenialReason.STORAGE_FAILURE
    assert str(error.value) == "Source content is unavailable."
    assert "private path" not in str(error.value)
    assert "SECRET-CONTENT" not in str(error.value)
    assert reader.iterations == 1
    assert reader.close_calls == 1
