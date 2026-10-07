"""Tests for configurable top-k selection and candidate ID preservation."""

import pytest

from evidence_layer.schemas import EvidenceCandidate
from evidence_layer.scoring.base import Scorer
from evidence_layer.selection import select_top_k


class StubScorer(Scorer):
    name = "stub"

    def __init__(self, score_map: dict[str, float]) -> None:
        self._map = score_map

    def score(self, query: str, text: str) -> float:
        return self._map.get(text, 0.0)


def _cand(cid: str, text: str) -> EvidenceCandidate:
    return EvidenceCandidate(
        candidate_id=cid, source_id="s", source_url="https://x/doc", text=text
    )


def test_select_top_k_returns_top_by_score():
    scorer = StubScorer({"a": 0.1, "b": 0.9, "c": 0.5})
    candidates = [_cand("c1", "a"), _cand("c2", "b"), _cand("c3", "c")]
    assert select_top_k(candidates, scorer, "q", 2) == ["c2", "c3"]


def test_select_top_k_respects_k():
    scorer = StubScorer({"a": 0.9, "b": 0.8, "c": 0.7})
    candidates = [_cand("c1", "a"), _cand("c2", "b"), _cand("c3", "c")]
    assert select_top_k(candidates, scorer, "q", 1) == ["c1"]
    assert len(select_top_k(candidates, scorer, "q", 2)) == 2


def test_select_top_k_tie_break_by_candidate_id_ascending():
    scorer = StubScorer({"a": 0.5, "b": 0.5})
    candidates = [_cand("c2", "b"), _cand("c1", "a")]
    assert select_top_k(candidates, scorer, "q", 2) == ["c1", "c2"]


def test_select_top_k_preserves_candidate_ids():
    scorer = StubScorer({"a": 0.9, "b": 0.1})
    candidates = [_cand("gold_1", "a"), _cand("d_2", "b")]
    selected = select_top_k(candidates, scorer, "q", 1)
    assert selected == ["gold_1"]
    candidate_ids = {c.candidate_id for c in candidates}
    assert set(selected) <= candidate_ids


@pytest.mark.parametrize("bad_k", [0, -1, -5])
def test_select_top_k_invalid_k_raises_value_error(bad_k):
    scorer = StubScorer({})
    with pytest.raises(ValueError):
        select_top_k([_cand("c1", "x")], scorer, "q", bad_k)


@pytest.mark.parametrize("bad_k", [1.5, "3", None, True])
def test_select_top_k_non_integer_k_raises_type_error(bad_k):
    scorer = StubScorer({})
    with pytest.raises(TypeError):
        select_top_k([_cand("c1", "x")], scorer, "q", bad_k)
