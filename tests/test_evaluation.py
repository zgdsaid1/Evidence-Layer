"""Tests for the evaluation harness: schema, reproducibility, split isolation."""

import json

import build_dataset
from evidence_layer.evaluation import (
    CSV_FIELDS,
    K_VALUES,
    build_report,
    evaluate_case,
    evaluate_cases,
    to_csv_rows,
)
from evidence_layer.schemas import EvaluationCase, EvidenceCandidate, Task
from evidence_layer.scoring.lexical import LexicalScorer

EXPECTED_METRIC_KEYS = {
    "n_cases",
    "recall_at_k",
    "precision_at_k",
    "mrr_at_k",
    "any_evidence_hit_rate",
    "full_evidence_rate",
    "mean_selected_evidence_count",
    "estimated_context_units_before",
    "estimated_context_units_after",
    "context_reduction_ratio",
    "failure_count",
}


def _case() -> EvaluationCase:
    candidates = [
        EvidenceCandidate(
            candidate_id="g", source_id="s", source_url="u", text="integer range data type"
        ),
        EvidenceCandidate(
            candidate_id="d1", source_id="s", source_url="u", text="banana split dessert"
        ),
    ]
    return EvaluationCase(
        case_id="c1",
        case_type="direct_factual",
        task=Task(
            task_id="t1", task_type="knowledge_query", domain="docs",
            input="what is the integer range",
        ),
        candidates=candidates,
        gold_candidate_ids=["g"],
        required_facts=["integer range"],
        source_urls=["u"],
    )


def test_evaluate_case_metrics_end_to_end():
    row = evaluate_case(_case(), LexicalScorer(), k=1)
    assert row["selected_candidate_ids"] == ["g"]
    assert row["recall_at_k"] == 1.0
    assert row["precision_at_k"] == 1.0
    assert row["no_gold_selected"] == 0
    assert row["all_estimated_context_units"] > row["selected_estimated_context_units"]


def test_build_report_schema():
    scorer = LexicalScorer()
    dev, _ = build_dataset.build_cases()
    report = build_report("dev", scorer.name, evaluate_cases(dev, scorer, K_VALUES))
    assert set(report.keys()) == {"split", "scorer", "k_values", "n_cases", "overall", "by_case_type"}
    assert report["split"] == "dev"
    assert report["scorer"] == "lexical_stopword_filtered"
    assert report["k_values"] == [1, 3, 5]
    assert report["n_cases"] == len(dev)
    for k in (1, 3, 5):
        assert set(report["overall"][f"k={k}"].keys()) == EXPECTED_METRIC_KEYS


def test_report_reproducible():
    dev, test = build_dataset.build_cases()
    r1 = evaluate_cases(dev + test, LexicalScorer(), K_VALUES)
    r2 = evaluate_cases(dev + test, LexicalScorer(), K_VALUES)
    assert json.dumps(r1, sort_keys=True) == json.dumps(r2, sort_keys=True)


def test_rows_count_is_cases_times_k():
    dev, test = build_dataset.build_cases()
    result = evaluate_cases(dev + test, LexicalScorer(), K_VALUES)
    assert len(result["rows"]) == 100 * len(K_VALUES)


def test_split_isolation_dev_test_disjoint():
    dev, test = build_dataset.build_cases()
    scorer = LexicalScorer()
    dev_ids = {r["task_id"] for r in evaluate_cases(dev, scorer, K_VALUES)["rows"]}
    test_ids = {r["task_id"] for r in evaluate_cases(test, scorer, K_VALUES)["rows"]}
    assert dev_ids.isdisjoint(test_ids)


def test_failure_count_matches_no_gold_selected():
    dev, test = build_dataset.build_cases()
    result = evaluate_cases(dev + test, LexicalScorer(), (1,))
    k1_rows = [r for r in result["rows"] if r["k"] == 1]
    assert result["overall"]["k=1"]["failure_count"] == sum(r["no_gold_selected"] for r in k1_rows)


def test_csv_rows_schema_and_count():
    dev, test = build_dataset.build_cases()
    result = evaluate_cases(dev + test, LexicalScorer(), K_VALUES)
    rows = to_csv_rows("dev", result["rows"])
    assert set(rows[0].keys()) == set(CSV_FIELDS)
    assert len(rows) == len(result["rows"])


def test_multi_gold_full_and_any_evidence():
    g1 = EvidenceCandidate(candidate_id="g1", source_id="s", source_url="u", text="integer range")
    g2 = EvidenceCandidate(candidate_id="g2", source_id="s", source_url="u", text="data type smallint")
    d = EvidenceCandidate(candidate_id="d1", source_id="s", source_url="u", text="banana split")
    case = EvaluationCase(
        case_id="c2",
        case_type="multi_source",
        task=Task(
            task_id="t2", task_type="knowledge_query", domain="docs",
            input="integer range and data type",
        ),
        candidates=[g1, g2, d],
        gold_candidate_ids=["g1", "g2"],
        required_facts=["integer range", "data type"],
        source_urls=["u"],
    )

    row1 = evaluate_case(case, LexicalScorer(), k=1)
    assert row1["full_evidence_rate"] == 0.0   # k=1 < 2 gold IDs
    assert row1["any_evidence_hit_rate"] == 1.0  # one gold selected

    row3 = evaluate_case(case, LexicalScorer(), k=3)
    assert row3["full_evidence_rate"] == 1.0   # all candidates -> both gold
    assert row3["any_evidence_hit_rate"] == 1.0

