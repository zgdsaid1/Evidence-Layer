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


LEVEL_NAMES = ("read uncommitted", "read committed", "repeatable read", "serializable")


def test_isolation_level_names_in_facts_are_supported_by_gold_text():
    dev, test = build_dataset.build_cases()
    for case in dev + test:
        facts = " ".join(case["required_facts"]).lower()
        gold_text = " ".join(
            c["text"] for c in case["candidates"] if c["candidate_id"] in case["gold_candidate_ids"]
        ).lower()
        for name in LEVEL_NAMES:
            if name in facts:
                assert name in gold_text, (case["case_id"], name)


def test_primary_key_index_claim_is_not_required_without_support():
    dev, test = build_dataset.build_cases()
    corpus = build_dataset.load_corpus()
    pk_text = next(p["text"] for p in corpus if p["passage_id"] == "pg_constr_pk").lower()
    assert "index" not in pk_text
    for case in dev + test:
        if "pg_constr_pk" in case["gold_candidate_ids"] and len(case["gold_candidate_ids"]) == 1:
            facts = " ".join(case["required_facts"]).lower()
            assert "index" not in facts and "btree" not in facts, case["case_id"]
        for fact in case["required_facts"]:
            if "primary key" in fact.lower():
                assert "btree" not in fact.lower(), case["case_id"]


def _membership(seed):
    corpus = build_dataset.load_corpus()
    corpus_map = {p["passage_id"]: p for p in corpus}
    cases = [
        build_dataset.build_case(spec, corpus, corpus_map, i)
        for i, spec in enumerate(build_dataset.SPECS)
    ]
    _, test = build_dataset.stratified_split(cases, build_dataset.DEV_FRACTION, seed)
    return {c["case_id"] for c in test}


def test_default_seed_reproduces_phase5b_heldout_membership():
    import json
    from pathlib import Path

    report = json.loads(
        (Path(build_dataset.ROOT) / "reports" / "phase5b_heldout_test_single_run.json").read_text()
    )
    expected = {row["record_id"] for row in report["per_candidate"]}
    assert _membership(build_dataset.SPLIT_SEED) == expected


def test_split_is_deterministic_per_seed():
    assert _membership(1) == _membership(1)


def test_split_seed_changes_membership():
    # The secondary sort used to be a case-ID tie-break that erased the shuffle,
    # making every seed yield the same split.
    memberships = {frozenset(_membership(seed)) for seed in range(20)}
    assert len(memberships) > 1


def test_split_keeps_gold_passages_disjoint_for_any_seed():
    cases = build_dataset.build_cases()[0] + build_dataset.build_cases()[1]
    for seed in (1, 9999, build_dataset.SPLIT_SEED):
        dev, test = build_dataset.stratified_split(cases, build_dataset.DEV_FRACTION, seed)
        dev_gold = {g for c in dev for g in c["gold_candidate_ids"]}
        test_gold = {g for c in test for g in c["gold_candidate_ids"]}
        assert dev_gold.isdisjoint(test_gold)
        assert len(dev) + len(test) == 100
