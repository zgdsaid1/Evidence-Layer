"""Evaluation harness for the local lexical baseline.

Runs a scorer + top-k selection over cases and aggregates the Phase 2 metrics,
grouped by case type. Development and held-out test sets are evaluated
independently; the held-out test set is used for *reporting only*, never for
tuning the algorithm.
"""

from __future__ import annotations

from collections import defaultdict

from evidence_layer.metrics import (
    any_evidence_hit_rate,
    context_reduction_ratio,
    estimated_context_units,
    full_evidence_rate,
    mrr_at_k,
    precision_at_k,
    recall_at_k,
)
from evidence_layer.schemas import EvaluationCase
from evidence_layer.scoring.base import Scorer
from evidence_layer.selection import select_top_k

#: The K values evaluated by the harness.
K_VALUES: tuple[int, ...] = (1, 3, 5)

#: CSV column order for per-case rows.
CSV_FIELDS = [
    "split",
    "query_id",
    "case_type",
    "k",
    "gold_candidate_ids",
    "selected_candidate_ids",
    "recall_at_k",
    "precision_at_k",
    "all_estimated_context_units",
    "selected_estimated_context_units",
    "context_reduction_ratio",
    "no_gold_selected",
]


def _ensure_case(raw) -> EvaluationCase:
    if isinstance(raw, EvaluationCase):
        return raw
    return EvaluationCase.model_validate(raw)


def evaluate_case(case: EvaluationCase, scorer: Scorer, k: int) -> dict:
    """Return one per-case metric row for a single k value."""
    query = case.task.input
    selected_ids = select_top_k(case.candidates, scorer, query, k)
    gold_ids = list(case.gold_candidate_ids)

    all_units = sum(estimated_context_units(c.text) for c in case.candidates)
    selected_units = sum(
        estimated_context_units(c.text)
        for c in case.candidates
        if c.candidate_id in selected_ids
    )

    return {
        "case_id": case.case_id,
        "task_id": case.task.task_id,
        "case_type": case.case_type,
        "k": k,
        "gold_candidate_ids": gold_ids,
        "selected_candidate_ids": selected_ids,
        "recall_at_k": recall_at_k(gold_ids, selected_ids),
        "precision_at_k": precision_at_k(gold_ids, selected_ids),
        "mrr_at_k": mrr_at_k(gold_ids, selected_ids),
        "any_evidence_hit_rate": any_evidence_hit_rate(gold_ids, selected_ids),
        "full_evidence_rate": full_evidence_rate(gold_ids, selected_ids),
        "all_estimated_context_units": all_units,
        "selected_estimated_context_units": selected_units,
        "context_reduction_ratio": context_reduction_ratio(all_units, selected_units),
        "no_gold_selected": int(not (set(gold_ids) & set(selected_ids))),
    }


def _aggregate(rows: list[dict]) -> dict:
    if not rows:
        return {
            "n_cases": 0,
            "recall_at_k": 0.0,
            "precision_at_k": 0.0,
            "mrr_at_k": 0.0,
            "any_evidence_hit_rate": 0.0,
            "full_evidence_rate": 0.0,
            "mean_selected_evidence_count": 0.0,
            "estimated_context_units_before": 0,
            "estimated_context_units_after": 0,
            "context_reduction_ratio": 0.0,
            "failure_count": 0,
        }

    before = sum(r["all_estimated_context_units"] for r in rows)
    after = sum(r["selected_estimated_context_units"] for r in rows)
    return {
        "n_cases": len(rows),
        "recall_at_k": round(sum(r["recall_at_k"] for r in rows) / len(rows), 6),
        "precision_at_k": round(sum(r["precision_at_k"] for r in rows) / len(rows), 6),
        "mrr_at_k": round(sum(r["mrr_at_k"] for r in rows) / len(rows), 6),
        "any_evidence_hit_rate": round(
            sum(r["any_evidence_hit_rate"] for r in rows) / len(rows), 6
        ),
        "full_evidence_rate": round(
            sum(r["full_evidence_rate"] for r in rows) / len(rows), 6
        ),
        "mean_selected_evidence_count": round(
            sum(len(r["selected_candidate_ids"]) for r in rows) / len(rows), 6
        ),
        "estimated_context_units_before": before,
        "estimated_context_units_after": after,
        "context_reduction_ratio": round(1 - (after / before), 6) if before else 0.0,
        "failure_count": sum(r["no_gold_selected"] for r in rows),
    }


def evaluate_cases(cases, scorer: Scorer, ks: tuple[int, ...] = K_VALUES) -> dict:
    """Evaluate every case at every k.

    Returns a dict with ``n_cases``, ``k_values``, ``overall``,
    ``by_case_type``, and ``rows`` (per-case rows for CSV export).
    """
    cases = [_ensure_case(c) for c in cases]

    rows: list[dict] = []
    for case in cases:
        for k in ks:
            rows.append(evaluate_case(case, scorer, k))

    case_types = sorted({case.case_type for case in cases})
    overall: dict[str, dict] = {}
    by_case_type: dict[str, dict] = defaultdict(dict)

    for k in ks:
        k_rows = [r for r in rows if r["k"] == k]
        overall[f"k={k}"] = _aggregate(k_rows)
        for case_type in case_types:
            ct_rows = [r for r in k_rows if r["case_type"] == case_type]
            by_case_type[case_type][f"k={k}"] = _aggregate(ct_rows)

    return {
        "n_cases": len(cases),
        "k_values": list(ks),
        "overall": overall,
        "by_case_type": dict(by_case_type),
        "rows": rows,
    }


def build_report(split: str, scorer_name: str, result: dict) -> dict:
    """Turn an ``evaluate_cases`` result into a JSON-ready report."""
    return {
        "split": split,
        "scorer": scorer_name,
        "k_values": result["k_values"],
        "n_cases": result["n_cases"],
        "overall": result["overall"],
        "by_case_type": result["by_case_type"],
    }


def to_csv_rows(split: str, rows: list[dict]) -> list[dict]:
    """Flatten per-case rows into CSV-ready dicts (lists joined with ``;``)."""
    out = []
    for r in rows:
        out.append(
            {
                "split": split,
                "query_id": r["task_id"],
                "case_type": r["case_type"],
                "k": r["k"],
                "gold_candidate_ids": ";".join(r["gold_candidate_ids"]),
                "selected_candidate_ids": ";".join(r["selected_candidate_ids"]),
                "recall_at_k": round(r["recall_at_k"], 6),
                "precision_at_k": round(r["precision_at_k"], 6),
                "all_estimated_context_units": r["all_estimated_context_units"],
                "selected_estimated_context_units": r["selected_estimated_context_units"],
                "context_reduction_ratio": round(r["context_reduction_ratio"], 6),
                "no_gold_selected": r["no_gold_selected"],
            }
        )
    return out
