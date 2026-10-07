"""Tests for the Phase 2 metric definitions, including zero denominators."""

import pytest

from evidence_layer.metrics import (
    any_evidence_hit_rate,
    context_reduction_ratio,
    estimated_context_units,
    full_evidence_rate,
    mrr_at_k,
    precision_at_k,
    recall_at_k,
)


def test_recall_at_k_exact():
    assert recall_at_k(["a", "b"], ["a", "c"]) == 0.5
    assert recall_at_k(["a"], ["a"]) == 1.0
    assert recall_at_k(["a"], ["b"]) == 0.0


def test_recall_at_k_zero_gold_denominator():
    assert recall_at_k([], ["a"]) == 0.0


def test_precision_at_k_exact():
    assert precision_at_k(["a", "b"], ["a", "c"]) == 0.5
    assert precision_at_k(["a"], ["a"]) == 1.0
    assert precision_at_k(["a", "b"], ["a", "b", "c"]) == 2 / 3


def test_precision_at_k_zero_selected_denominator():
    assert precision_at_k(["a"], []) == 0.0


def test_context_reduction_ratio():
    assert context_reduction_ratio(100, 20) == 0.8
    assert context_reduction_ratio(100, 0) == 1.0


def test_context_reduction_ratio_zero_all_units():
    assert context_reduction_ratio(0, 0) == 0.0


def test_estimated_context_units_is_whitespace_word_count():
    assert estimated_context_units("one two three") == 3
    assert estimated_context_units("") == 0
    assert estimated_context_units("  spaced   out  ") == 2


def test_mrr_at_k():
    assert mrr_at_k(["a"], ["a", "b", "c"]) == 1.0
    assert mrr_at_k(["b"], ["a", "b", "c"]) == 0.5
    assert mrr_at_k(["c"], ["a", "b", "c"]) == pytest.approx(1 / 3)
    assert mrr_at_k(["d"], ["a", "b", "c"]) == 0.0


def test_any_evidence_hit_rate():
    assert any_evidence_hit_rate(["a", "b"], ["a"]) == 1.0
    assert any_evidence_hit_rate(["a", "b"], ["c"]) == 0.0


def test_full_evidence_rate():
    assert full_evidence_rate(["a"], ["a"]) == 1.0
    assert full_evidence_rate(["a", "b"], ["a", "b", "c"]) == 1.0
    assert full_evidence_rate(["a", "b"], ["a", "c"]) == 0.0


def test_full_evidence_rate_below_gold_count_is_zero():
    # k=1 < 2 gold IDs -> all gold cannot be selected, so full rate is 0.0
    assert full_evidence_rate(["a", "b"], ["a"]) == 0.0


def test_full_evidence_rate_zero_gold_denominator():
    assert full_evidence_rate([], ["a"]) == 0.0

