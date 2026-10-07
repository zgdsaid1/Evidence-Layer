"""Tests for LocalCorpusRetriever using a small synthetic corpus."""

import json

import pytest

from evidence_layer.retrieval import LocalCorpusRetriever
from evidence_layer.schemas import EvidenceCandidate
from evidence_layer.scoring.lexical import LexicalScorer
from evidence_layer.selection import select_top_k

RECORDS = [
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
    {
        "passage_id": "p_vacuum",
        "source_id": "src/2",
        "source_url": "https://example.test/vacuum",
        "text": "vacuum reclaims dead storage",
    },
]


@pytest.fixture
def retriever(tmp_path):
    path = tmp_path / "corpus.jsonl"
    path.write_text("\n".join(json.dumps(r) for r in RECORDS) + "\n", encoding="utf-8")
    return LocalCorpusRetriever(path)


def test_relevant_query_returns_ranked_evidence(retriever):
    result = retriever.retrieve("btree index lookups", top_k=5, budget_words=500)
    assert result.status == "ok"
    ids = [e.evidence_id for e in result.evidence]
    assert "p_vacuum" not in ids
    scores = [e.score for e in result.evidence]
    assert scores == sorted(scores, reverse=True)
    assert ids[0] == "p_index"


def test_no_match_returns_no_results(retriever):
    result = retriever.retrieve("zebra giraffe")
    assert result.status == "no_results"
    assert result.evidence == []


@pytest.mark.parametrize("query", ["", "   ", "\n\t"])
def test_empty_query_rejected(retriever, query):
    with pytest.raises(ValueError, match="query"):
        retriever.retrieve(query)


@pytest.mark.parametrize("top_k", [0, -1, True, 1.5])
def test_invalid_top_k_rejected(retriever, top_k):
    with pytest.raises((ValueError, TypeError), match="top_k"):
        retriever.retrieve("index", top_k=top_k)


@pytest.mark.parametrize("budget", [0, -5, True, 2.0])
def test_invalid_budget_rejected(retriever, budget):
    with pytest.raises((ValueError, TypeError), match="budget_words"):
        retriever.retrieve("index", budget_words=budget)


def test_top_k_is_respected(retriever):
    result = retriever.retrieve("btree index lookups", top_k=1)
    assert len(result.evidence) == 1


def test_budget_words_is_respected(retriever):
    result = retriever.retrieve("btree index lookups", budget_words=10)
    assert sum(len(e.text.split()) for e in result.evidence) <= 10
    assert result.used_words == sum(len(e.text.split()) for e in result.evidence)


def test_large_candidate_does_not_block_smaller_later_one(retriever):
    # p_index_long ranks first but exceeds the budget; p_index must still be chosen.
    full = retriever.retrieve("btree index", top_k=5, budget_words=500)
    assert full.evidence[0].evidence_id == "p_index_long"
    small = retriever.retrieve("btree index", top_k=5, budget_words=10)
    assert [e.evidence_id for e in small.evidence] == ["p_index"]
    assert small.status == "ok"


def test_evidence_id_and_citation_come_from_source_record(retriever):
    result = retriever.retrieve("btree index lookups")
    by_id = {r["passage_id"]: r for r in RECORDS}
    for e in result.evidence:
        src = by_id[e.evidence_id]
        assert (e.source_id, e.source_url, e.text) == (
            src["source_id"], src["source_url"], src["text"]
        )
        assert e.section == src.get("section")
    vac = retriever.retrieve("vacuum").evidence[0]
    assert vac.section is None


def test_tiny_budget_returns_budget_exhausted(retriever):
    result = retriever.retrieve("btree index lookups", budget_words=1)
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
