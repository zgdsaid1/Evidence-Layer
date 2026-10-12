"""Configurable top-k evidence selection.

``k`` is configurable, validated at call time, and never hard-coded in the
schemas. Candidate IDs and source attribution are preserved unchanged; only the
*order* of candidates is decided here.
"""

from __future__ import annotations

from collections.abc import Sequence

from evidence_layer.scoring.base import Scorer
from evidence_layer.schemas import EvidenceCandidate


def _validate_k(k: int) -> None:
    if isinstance(k, bool) or not isinstance(k, int):
        raise TypeError(f"k must be an integer, got {type(k).__name__}")
    if k < 1:
        raise ValueError(f"k must be >= 1, got {k}")


def select_top_k(
    candidates: list[EvidenceCandidate],
    scorer: Scorer,
    query: str,
    k: int,
) -> list[str]:
    """Return the candidate IDs of the top-``k`` candidates by score.

    Ties are broken by ``candidate_id`` ascending so the result is
    deterministic for a fixed input.
    """
    _validate_k(k)
    scores = [scorer.score(query, candidate.text) for candidate in candidates]
    return select_top_k_scored(candidates, scores, k)


def select_top_k_scored(
    candidates: list[EvidenceCandidate], scores: Sequence[float], k: int
) -> list[str]:
    """Return top candidate IDs for scores aligned with ``candidates``."""
    _validate_k(k)
    if len(scores) != len(candidates):
        raise ValueError("scores must contain one value for each candidate")

    scored = [
        (score, candidate.candidate_id)
        for candidate, score in zip(candidates, scores)
    ]
    scored.sort(key=lambda pair: (-pair[0], pair[1]))
    return [candidate_id for _, candidate_id in scored[:k]]