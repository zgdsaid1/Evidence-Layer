"""Metric definitions for the Phase 2 lexical baseline harness.

``estimated_context_units`` is a whitespace word count ONLY. It is deliberately
not called a token count (no tokenizer is used).
"""

from __future__ import annotations


def estimated_context_units(text: str) -> int:
    """Whitespace word count of ``text`` (an estimated context size, not tokens)."""
    return len(text.split())


def recall_at_k(gold_ids: list[str], selected_ids: list[str]) -> float:
    """|gold ∩ selected| / |gold|.

    Returns 0.0 when there is no gold evidence (zero denominator).
    """
    gold = set(gold_ids)
    if not gold:
        return 0.0
    return len(gold & set(selected_ids)) / len(gold)


def precision_at_k(gold_ids: list[str], selected_ids: list[str]) -> float:
    """|gold ∩ selected| / |selected|.

    Returns 0.0 when nothing was selected (zero denominator).
    """
    selected = set(selected_ids)
    if not selected:
        return 0.0
    return len(set(gold_ids) & selected) / len(selected)


def context_reduction_ratio(all_units: int, selected_units: int) -> float:
    """1 - selected_units / all_units.

    Returns 0.0 when ``all_units`` is zero (zero denominator).
    """
    if all_units <= 0:
        return 0.0
    return 1.0 - (selected_units / all_units)


def mrr_at_k(gold_ids: list[str], selected_ids: list[str]) -> float:
    """Reciprocal rank of the first selected gold candidate (1-based).

    Returns 0.0 if no gold candidate is selected.
    """
    gold = set(gold_ids)
    for rank, candidate_id in enumerate(selected_ids, start=1):
        if candidate_id in gold:
            return 1.0 / rank
    return 0.0


def any_evidence_hit_rate(gold_ids: list[str], selected_ids: list[str]) -> float:
    """Per-case 1.0 if at least one gold candidate is selected, else 0.0.

    The aggregate mean over cases is the any-evidence hit rate.
    """
    return 1.0 if (set(gold_ids) & set(selected_ids)) else 0.0


def full_evidence_rate(gold_ids: list[str], selected_ids: list[str]) -> float:
    """Per-case 1.0 if *all* gold candidates are selected, else 0.0.

    The aggregate mean over cases is the full-evidence rate. When ``k`` is
    smaller than the number of gold IDs this is legitimately 0.0. Returns 0.0
    when there is no gold evidence (zero denominator).
    """
    gold = set(gold_ids)
    if not gold:
        return 0.0
    return 1.0 if gold <= set(selected_ids) else 0.0

