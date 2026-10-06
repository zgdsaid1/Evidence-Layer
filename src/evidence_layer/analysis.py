"""Read-only split-audit and sensitivity analysis.

These functions only *observe* the dataset and scorer outputs. They never
mutate cases and never use the held-out test set to select or tune a scorer.

Lexical overlap is measured with a stopword-agnostic token Jaccard similarity
so the audit is independent of the baseline scorer's stopword choice.
"""

from __future__ import annotations

import re
from collections import Counter
from statistics import mean

from evidence_layer.evaluation import K_VALUES, evaluate_cases
from evidence_layer.scoring.base import Scorer

_TOKEN = re.compile(r"[a-z0-9]+")


def _stats(values) -> dict:
    values = list(values)
    if not values:
        return {"count": 0, "min": 0, "max": 0, "mean": 0.0}
    return {
        "count": len(values),
        "min": min(values),
        "max": max(values),
        "mean": round(mean(values), 6),
    }


def _norm_query(query: str) -> str:
    return " ".join(query.lower().split())


def _query_tokens(query: str) -> set[str]:
    return set(_TOKEN.findall(query.lower()))


def _jaccard(a: set, b: set) -> float:
    union = a | b
    if not union:
        return 0.0
    return len(a & b) / len(union)


def _token_overlap(query: str, text: str) -> float:
    return _jaccard(_query_tokens(query), _query_tokens(text))


def _question_template(query: str) -> str:
    words = _TOKEN.findall(query.lower())
    if not words:
        return "(empty)"
    return f"{words[0]} {words[1]}" if len(words) >= 2 else words[0]


def _audit_split(cases: list[dict]) -> dict:
    case_types = Counter(c["case_type"] for c in cases)
    gold_ids_per_case = [len(c["gold_candidate_ids"]) for c in cases]
    candidate_count_per_case = [len(c["candidates"]) for c in cases]
    query_word_counts = [len(c["task"]["input"].split()) for c in cases]
    candidate_word_counts = [
        len(cand["text"].split()) for c in cases for cand in c["candidates"]
    ]

    query_to_gold: list[float] = []
    query_to_distractor: list[float] = []
    for c in cases:
        query = c["task"]["input"]
        gold = set(c["gold_candidate_ids"])
        gold_overlaps = [
            _token_overlap(query, cand["text"])
            for cand in c["candidates"]
            if cand["candidate_id"] in gold
        ]
        distractor_overlaps = [
            _token_overlap(query, cand["text"])
            for cand in c["candidates"]
            if cand["candidate_id"] not in gold
        ]
        query_to_gold.append(mean(gold_overlaps) if gold_overlaps else 0.0)
        query_to_distractor.append(mean(distractor_overlaps) if distractor_overlaps else 0.0)

    templates = Counter(_question_template(c["task"]["input"]) for c in cases)
    repeated_templates = {k: v for k, v in templates.items() if v >= 2}

    return {
        "n_cases": len(cases),
        "case_type_counts": dict(case_types),
        "gold_ids_per_case": _stats(gold_ids_per_case),
        "candidate_count_per_case": _stats(candidate_count_per_case),
        "query_word_count": _stats(query_word_counts),
        "candidate_word_count": _stats(candidate_word_counts),
        "query_to_gold_overlap": _stats(query_to_gold),
        "query_to_distractor_overlap": _stats(query_to_distractor),
        "repeated_template_count": len(repeated_templates),
        "repeated_templates": repeated_templates,
    }


def _query_duplication(cases: list[dict]) -> dict:
    queries = [_norm_query(c["task"]["input"]) for c in cases]
    exact_dupes = sum(1 for _, n in Counter(queries).items() if n > 1)
    token_sets = [_query_tokens(q) for q in queries]
    near_pairs = sum(
        1
        for i in range(len(token_sets))
        for j in range(i + 1, len(token_sets))
        if _jaccard(token_sets[i], token_sets[j]) > 0.8
    )
    return {
        "exact_duplicate_query_count": exact_dupes,
        "near_duplicate_query_pairs": near_pairs,
    }


def _cross_split_duplication(dev_cases: list[dict], test_cases: list[dict]) -> dict:
    dev_queries = [_norm_query(c["task"]["input"]) for c in dev_cases]
    test_queries = [_norm_query(c["task"]["input"]) for c in test_cases]
    exact = len(set(dev_queries) & set(test_queries))
    dev_tokens = [_query_tokens(q) for q in dev_queries]
    test_tokens = [_query_tokens(q) for q in test_queries]
    near = sum(
        1
        for a in dev_tokens
        for b in test_tokens
        if _jaccard(a, b) > 0.8
    )
    return {
        "exact_duplicate_queries_across_splits": exact,
        "near_duplicate_query_pairs_across_splits": near,
    }


def compute_split_audit(dev_cases: list[dict], test_cases: list[dict]) -> dict:
    """Produce a read-only dev-vs-test comparison report."""
    dev = _audit_split(dev_cases)
    test = _audit_split(test_cases)
    dev["duplicate_query_indicators"] = _query_duplication(dev_cases)
    test["duplicate_query_indicators"] = _query_duplication(test_cases)
    return {
        "dev": dev,
        "test": test,
        "cross_split": _cross_split_duplication(dev_cases, test_cases),
    }


def compute_sensitivity(
    dev_cases: list[dict],
    variants: dict[str, Scorer],
    ks: tuple[int, ...] = K_VALUES,
) -> dict:
    """Evaluate each variant on the development split only (for interpretation)."""
    out: dict[str, dict] = {}
    for name, scorer in variants.items():
        result = evaluate_cases(dev_cases, scorer, ks)
        out[name] = {
            "overall": result["overall"],
            "by_case_type": result["by_case_type"],
        }
    return out


SENSITIVITY_CSV_FIELDS = [
    "variant",
    "k",
    "n_cases",
    "recall_at_k",
    "precision_at_k",
    "mrr_at_k",
    "any_evidence_hit_rate",
    "full_evidence_rate",
    "failure_count",
    "mean_selected_evidence_count",
    "estimated_context_units_before",
    "estimated_context_units_after",
    "context_reduction_ratio",
]


def sensitivity_csv_rows(sensitivity: dict, ks: tuple[int, ...] = K_VALUES) -> list[dict]:
    rows: list[dict] = []
    for variant, data in sensitivity.items():
        for k in ks:
            m = data["overall"][f"k={k}"]
            rows.append(
                {
                    "variant": variant,
                    "k": k,
                    "n_cases": m["n_cases"],
                    "recall_at_k": m["recall_at_k"],
                    "precision_at_k": m["precision_at_k"],
                    "mrr_at_k": m["mrr_at_k"],
                    "any_evidence_hit_rate": m["any_evidence_hit_rate"],
                    "full_evidence_rate": m["full_evidence_rate"],
                    "failure_count": m["failure_count"],
                    "mean_selected_evidence_count": m["mean_selected_evidence_count"],
                    "estimated_context_units_before": m["estimated_context_units_before"],
                    "estimated_context_units_after": m["estimated_context_units_after"],
                    "context_reduction_ratio": m["context_reduction_ratio"],
                }
            )
    return rows
