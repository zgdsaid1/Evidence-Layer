"""Tests for split-audit and sensitivity analysis (read-only, non-mutating)."""

import copy
import json

import build_dataset
from evidence_layer.analysis import (
    SENSITIVITY_CSV_FIELDS,
    compute_sensitivity,
    compute_split_audit,
    sensitivity_csv_rows,
)
from evidence_layer.evaluation import K_VALUES
from evidence_layer.scoring.lexical import LexicalNoStopwordScorer, LexicalScorer


def _variants():
    return {
        "lexical_stopword_filtered": LexicalScorer(),
        "lexical_no_stopword_filter": LexicalNoStopwordScorer(),
    }


def test_split_audit_schema():
    dev, test = build_dataset.build_cases()
    audit = compute_split_audit(dev, test)
    assert set(audit.keys()) == {"dev", "test", "cross_split"}
    for split in ("dev", "test"):
        d = audit[split]
        assert set(d.keys()) == {
            "n_cases",
            "case_type_counts",
            "gold_ids_per_case",
            "candidate_count_per_case",
            "query_word_count",
            "candidate_word_count",
            "query_to_gold_overlap",
            "query_to_distractor_overlap",
            "repeated_template_count",
            "repeated_templates",
            "duplicate_query_indicators",
        }
    assert set(audit["cross_split"].keys()) == {
        "exact_duplicate_queries_across_splits",
        "near_duplicate_query_pairs_across_splits",
    }


def test_split_audit_does_not_mutate_cases():
    dev, test = build_dataset.build_cases()
    dev_before = copy.deepcopy(dev)
    test_before = copy.deepcopy(test)
    compute_split_audit(dev, test)
    assert dev == dev_before
    assert test == test_before


def test_split_audit_reproducible():
    dev, test = build_dataset.build_cases()
    a1 = compute_split_audit(dev, test)
    a2 = compute_split_audit(dev, test)
    assert json.dumps(a1, sort_keys=True) == json.dumps(a2, sort_keys=True)


def test_sensitivity_has_two_variants_on_dev():
    dev, _ = build_dataset.build_cases()
    sens = compute_sensitivity(dev, _variants(), K_VALUES)
    assert set(sens.keys()) == {"lexical_stopword_filtered", "lexical_no_stopword_filter"}
    for data in sens.values():
        assert set(data.keys()) == {"overall", "by_case_type"}


def test_sensitivity_csv_rows_schema_and_count():
    dev, _ = build_dataset.build_cases()
    sens = compute_sensitivity(dev, _variants(), K_VALUES)
    rows = sensitivity_csv_rows(sens, K_VALUES)
    assert len(rows) == 2 * len(K_VALUES)
    assert set(rows[0].keys()) == set(SENSITIVITY_CSV_FIELDS)
