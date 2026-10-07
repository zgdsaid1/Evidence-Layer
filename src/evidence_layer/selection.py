"""Configurable top-k evidence selection.

``k`` is configurable, validated at call time, and never hard-coded in the
schemas. Candidate IDs and source attribution are preserved unchanged; only the
*order* of candidates is decided here.
"""

from __future__ import annotations

from evidence_layer.scoring.base import Scorer
from evidence_layer.schemas import EvidenceCandidate


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
    if isinstance(k, bool) or not isinstance(k, int):
        raise TypeError(f"k must be an integer, got {type(k).__name__}")
    if k < 1:
        raise ValueError(f"k must be >= 1, got {k}")

    scored = [(scorer.score(query, c.text), c.candidate_id) for c in candidates]
    scored.sort(key=lambda pair: (-pair[0], pair[1]))
    return [candidate_id for _, candidate_id in scored[:k]]
