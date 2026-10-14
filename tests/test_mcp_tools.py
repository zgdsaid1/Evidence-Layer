"""Tests for the transport-free ``retrieve_evidence`` tool adapter.

These tests exercise the adapter boundary only: strict validation, deterministic
mapping to the existing local retriever, and safe error classification. They
make no network calls and do not touch Supabase, Vercel, Jev, environment
variables, or secrets.
"""

import inspect

import pytest

import evidence_layer.mcp.tools as tools_module
from evidence_layer.retrieval import LocalCorpusRetriever
from evidence_layer.mcp.tools import retrieve_evidence


def test_valid_query_fails_closed_without_classified_source():
    result = retrieve_evidence("btree index")
    assert result == {
        "error": {
            "code": "source_unavailable",
            "message": "local source is unavailable",
        }
    }


def test_determinism():
    assert retrieve_evidence("btree index") == retrieve_evidence("btree index")


def test_no_results_query_still_denies_unclassified_source():
    result = retrieve_evidence("zzzxqvnonexistenttoken")
    assert result["error"]["code"] == "source_unavailable"


def test_mcp_does_not_open_an_unclassified_corpus(monkeypatch):
    from evidence_layer.retrieval import synthetic_fixtures

    opened = []

    def tracked_open(path, *args, **kwargs):
        opened.append(path)
        raise AssertionError("MCP must not open an unclassified corpus")

    monkeypatch.setattr(synthetic_fixtures.os, "open", tracked_open)
    result = retrieve_evidence("btree index")

    assert result["error"]["code"] == "source_unavailable"
    assert opened == []


def test_standard_mcp_does_not_opt_in_to_synthetic_fixture(monkeypatch):
    def forbidden_fixture_factory(*args, **kwargs):
        raise AssertionError("standard MCP must not use the development fixture")

    monkeypatch.setattr(
        LocalCorpusRetriever,
        "for_synthetic_development_fixture",
        forbidden_fixture_factory,
    )
    result = retrieve_evidence("btree index")

    assert result["error"]["code"] == "source_unavailable"


@pytest.mark.parametrize("query", ["", "   ", "\n\t", 5, None, ["query"], b"bytes"])
def test_invalid_query_returns_error(query):
    result = retrieve_evidence(query)
    assert result == {
        "error": {
            "code": "invalid_argument",
            "message": "query must be a non-empty string",
        }
    }


@pytest.mark.parametrize("top_k", [0, 21, True, 1.5, "5"])
def test_invalid_top_k_returns_error(top_k):
    result = retrieve_evidence("btree index", top_k=top_k)
    assert result == {
        "error": {
            "code": "invalid_argument",
            "message": "top_k must be an integer between 1 and 20",
        }
    }


@pytest.mark.parametrize("budget_words", [0, 20001, True, 1.5, "500"])
def test_invalid_budget_words_returns_error(budget_words):
    result = retrieve_evidence("btree index", budget_words=budget_words)
    assert result == {
        "error": {
            "code": "invalid_argument",
            "message": "budget_words must be an integer between 1 and 20000",
        }
    }


class _FakeCorpusFailure:
    def __init__(self):
        raise ValueError("corpus parse failure at /tmp/secret/corpus.jsonl")


def test_corpus_failure_maps_to_corpus_unavailable(monkeypatch):
    monkeypatch.setattr(tools_module, "LocalCorpusRetriever", _FakeCorpusFailure)
    result = retrieve_evidence("btree index")
    assert result == {
        "error": {
            "code": "corpus_unavailable",
            "message": "local corpus is unavailable",
        }
    }


def test_jev_fallback_metadata_is_reported_without_provider_error_body(monkeypatch):
    from evidence_layer.scoring.policy import build_provider_selection_policy

    secret = "SYNTHETIC_SECRET_PROVIDER_BODY"

    class FailingScorer:
        name = "jev"

        def __init__(self):
            self.calls = []

        def score(self, query, text):
            self.calls.append((query, text))
            raise AssertionError("Phase 1 must not invoke an injected JEV scorer")

    failing_scorer = FailingScorer()

    real_retriever = tools_module.LocalCorpusRetriever

    def retriever_with_failing_jev():
        return real_retriever(
            ("unclassified-source",),
            scoring_policy=build_provider_selection_policy(
                jev_enabled=True,
                jev_permitted_by_request=True,
                jev_permitted_by_plan=True,
                jev_scorer=failing_scorer,
            )
        )

    monkeypatch.setattr(
        tools_module, "LocalCorpusRetriever", retriever_with_failing_jev
    )
    result = retrieve_evidence("btree index")

    assert result["error"]["code"] == "source_unavailable"
    assert secret not in repr(result)
    assert failing_scorer.calls == []


def test_standard_mcp_adapter_never_invokes_direct_jev_scorer(monkeypatch):
    from evidence_layer.scoring.jev import JevEvidenceScorer

    calls = []

    def forbidden_score(self, query, text):
        calls.append((query, text))
        raise AssertionError("standard MCP must remain lexical-only")

    monkeypatch.setattr(JevEvidenceScorer, "score", forbidden_score)
    result = retrieve_evidence("btree index")

    assert result["error"]["code"] == "source_unavailable"
    assert calls == []


class _FakeInternalFailure:
    def __init__(self):
        pass

    def retrieve(self, query, *, request_context=None, top_k=5, budget_words=500):
        raise RuntimeError("SECRET sk-1234567890 /home/secret/token")


def test_unexpected_failure_maps_to_internal_error(monkeypatch):
    monkeypatch.setattr(tools_module, "LocalCorpusRetriever", _FakeInternalFailure)
    result = retrieve_evidence("btree index")
    assert result == {
        "error": {"code": "internal_error", "message": "retrieve_evidence failed"}
    }
    rendered = repr(result)
    assert "SECRET" not in rendered
    assert "sk-1234567890" not in rendered
    assert "/home/secret/token" not in rendered


class _FakeResultAttributeFailure:
    def __init__(self):
        pass

    def retrieve(self, query, *, request_context=None, top_k=5, budget_words=500):
        return _ExplodingResult()


class _ExplodingResult:
    @property
    def status(self):
        raise RuntimeError("SECRET sk-9876543210 /home/secret/result.jsonl")


def test_result_conversion_failure_returns_internal_error(monkeypatch):
    monkeypatch.setattr(tools_module, "LocalCorpusRetriever", _FakeResultAttributeFailure)
    result = retrieve_evidence("btree index")
    assert result == {
        "error": {"code": "internal_error", "message": "retrieve_evidence failed"}
    }
    rendered = repr(result)
    assert "SECRET" not in rendered
    assert "sk-9876543210" not in rendered
    assert "/home/secret/result.jsonl" not in rendered


def test_no_network_or_external_imports():
    source = inspect.getsource(tools_module)
    for forbidden in ("typesafe_sdk", "supabase", "requests", "httpx", "urllib", "socket"):
        assert f"import {forbidden}" not in source
        assert f"from {forbidden}" not in source
