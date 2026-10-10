"""Tests for the transport-free ``retrieve_evidence`` tool adapter.

These tests exercise the adapter boundary only: strict validation, deterministic
mapping to the existing local retriever, and safe error classification. They
make no network calls and do not touch Supabase, Vercel, Jev, environment
variables, or secrets.
"""

import inspect

import pytest

import evidence_layer.mcp.tools as tools_module
from evidence_layer.mcp.tools import retrieve_evidence

SUCCESS_KEYS = {
    "status",
    "query",
    "top_k",
    "budget_words",
    "evidence",
    "candidate_count",
    "used_words",
}

EVIDENCE_KEYS = {
    "evidence_id",
    "text",
    "source_id",
    "source_url",
    "section",
    "score",
    "word_count",
}


def test_valid_retrieval_success_contract():
    result = retrieve_evidence("btree index")
    assert set(result.keys()) == SUCCESS_KEYS
    assert result["status"] == "ok"
    assert result["query"] == "btree index"
    assert result["top_k"] == 5
    assert result["budget_words"] == 500
    assert isinstance(result["candidate_count"], int)
    assert isinstance(result["used_words"], int)
    assert result["evidence"]
    assert len(result["evidence"]) <= result["top_k"]
    assert result["used_words"] <= result["budget_words"]
    assert result["candidate_count"] >= len(result["evidence"])


def test_evidence_item_contract():
    result = retrieve_evidence("btree index")
    assert result["status"] == "ok"
    for item in result["evidence"]:
        assert set(item.keys()) == EVIDENCE_KEYS
        assert isinstance(item["evidence_id"], str)
        assert isinstance(item["text"], str)
        assert isinstance(item["source_id"], str)
        assert isinstance(item["source_url"], str)
        assert item["section"] is None or isinstance(item["section"], str)
        assert isinstance(item["score"], float)
        assert isinstance(item["word_count"], int)
        assert item["word_count"] >= 1


def test_query_is_stripped():
    result = retrieve_evidence("   btree index   ")
    assert result["query"] == "btree index"


def test_determinism():
    assert retrieve_evidence("btree index") == retrieve_evidence("btree index")


def test_no_results_is_success_not_error():
    result = retrieve_evidence("zzzxqvnonexistenttoken")
    assert result["status"] == "no_results"
    assert result["evidence"] == []
    assert result["candidate_count"] == 0
    assert result["used_words"] == 0
    assert "error" not in result


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


class _FakeInternalFailure:
    def __init__(self):
        pass

    def retrieve(self, query, *, top_k=5, budget_words=500):
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


def test_no_network_or_external_imports():
    source = inspect.getsource(tools_module)
    for forbidden in ("typesafe_sdk", "supabase", "requests", "httpx", "urllib", "socket"):
        assert f"import {forbidden}" not in source
        assert f"from {forbidden}" not in source
