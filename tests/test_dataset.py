"""Integration tests for the evaluation dataset integrity."""

from collections import Counter

import build_dataset
import validate_dataset


def test_build_produces_100_cases():
    dev, test = build_dataset.build_cases()
    assert len(dev) + len(test) == 100
    assert 15 <= len(test) <= 25
    assert len(test) > 0


def test_case_type_distribution_matches_target():
    dev, test = build_dataset.build_cases()
    counts = Counter(c["case_type"] for c in dev + test)
    assert counts["direct_factual"] == 40
    assert counts["multi_source"] == 25
    assert counts["false_premise"] == 15
    assert counts["ambiguous"] == 10
    assert counts["prompt_injection"] == 10


def test_validate_cases_reports_no_errors():
    dev, test = build_dataset.build_cases()
    assert validate_dataset.validate_cases(dev) == []
    assert validate_dataset.validate_cases(test) == []


def test_no_dev_test_overlap():
    dev, test = build_dataset.build_cases()
    assert validate_dataset.check_overlap(dev, test) == []


def test_every_case_has_nonempty_query_passages_gold_facts_url():
    dev, test = build_dataset.build_cases()
    for case in dev + test:
        assert case["task"]["input"].strip()
        assert len(case["candidates"]) >= 1
        assert all(c["text"].strip() for c in case["candidates"])
        assert len(case["gold_candidate_ids"]) >= 1
        assert len(case["required_facts"]) >= 1
        assert len(case["source_urls"]) >= 1


def test_gold_ids_are_valid_candidate_ids():
    dev, test = build_dataset.build_cases()
    for case in dev + test:
        candidate_ids = {c["candidate_id"] for c in case["candidates"]}
        assert set(case["gold_candidate_ids"]) <= candidate_ids


def test_injection_cases_have_disjoint_untrusted_candidates():
    dev, test = build_dataset.build_cases()
    injection_cases = [c for c in dev + test if c["case_type"] == "prompt_injection"]
    assert len(injection_cases) == 10
    for case in injection_cases:
        assert case["untrusted_candidate_ids"]
        candidate_ids = {c["candidate_id"] for c in case["candidates"]}
        assert set(case["untrusted_candidate_ids"]) <= candidate_ids
        assert not (set(case["untrusted_candidate_ids"]) & set(case["gold_candidate_ids"]))
