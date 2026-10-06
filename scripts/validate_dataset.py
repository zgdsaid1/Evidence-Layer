#!/usr/bin/env python3
"""Validate the generated evaluation dataset.

Checks:
  * Pydantic schema validity (every case parses as an ``EvaluationCase``)
  * unique task IDs (within and across dev/test)
  * non-empty queries and passages
  * valid gold candidate IDs (each gold id is present among the candidates)
  * required facts are present and non-empty
  * case-type distribution matches the target
  * no overlap / near-duplicate passage sets between dev and test

Run:  python scripts/validate_dataset.py
Exit code is 0 on success, 1 on any hard failure.
"""

from __future__ import annotations

import json
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from evidence_layer.schemas import EvaluationCase  # noqa: E402

CORPUS_PATH = ROOT / "data" / "corpus" / "postgresql_passages.jsonl"
DEV_PATH = ROOT / "data" / "dev" / "cases.jsonl"
TEST_PATH = ROOT / "data" / "test" / "cases.jsonl"

TARGET_DISTRIBUTION = {
    "direct_factual": 0.40,
    "multi_source": 0.25,
    "false_premise": 0.15,
    "ambiguous": 0.10,
    "prompt_injection": 0.10,
}
# Exact counts for a 100-case dataset.
TARGET_COUNTS = {k: round(v * 100) for k, v in TARGET_DISTRIBUTION.items()}


def load_jsonl(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]


def validate_cases(cases: list[dict]) -> list[str]:
    errors: list[str] = []
    task_ids: list[str] = []

    for raw in cases:
        try:
            case = EvaluationCase.model_validate(raw)
        except Exception as exc:  # noqa: BLE001
            errors.append(f"{raw.get('case_id', '?')}: schema invalid: {exc}")
            continue

        task_ids.append(case.task.task_id)

        if not case.task.input.strip():
            errors.append(f"{case.case_id}: empty query")

        if not case.candidates:
            errors.append(f"{case.case_id}: no retrieved passages")
        for cand in case.candidates:
            if not cand.text.strip():
                errors.append(f"{case.case_id}: candidate {cand.candidate_id} has empty text")
            if not cand.source_url.strip():
                errors.append(f"{case.case_id}: candidate {cand.candidate_id} missing source_url")

        if not case.gold_candidate_ids:
            errors.append(f"{case.case_id}: no gold passage IDs")

        if not case.required_facts or any(not f.strip() for f in case.required_facts):
            errors.append(f"{case.case_id}: required facts missing or empty")

        if not case.source_urls:
            errors.append(f"{case.case_id}: no source URL")

        candidate_ids = {c.candidate_id for c in case.candidates}
        for gold in case.gold_candidate_ids:
            if gold not in candidate_ids:
                errors.append(f"{case.case_id}: gold id {gold} not among candidates")

        for untrusted in case.untrusted_candidate_ids:
            if untrusted not in candidate_ids:
                errors.append(f"{case.case_id}: untrusted id {untrusted} not among candidates")
            if untrusted in case.gold_candidate_ids:
                errors.append(f"{case.case_id}: untrusted id {untrusted} is also gold")

    if len(task_ids) != len(set(task_ids)):
        dupes = [t for t, n in Counter(task_ids).items() if n > 1]
        errors.append(f"duplicate task IDs: {dupes}")

    return errors


def distribution(cases: list[dict]) -> Counter:
    return Counter(c["case_type"] for c in cases)


def check_distribution(cases: list[dict]) -> list[str]:
    errors: list[str] = []
    counts = distribution(cases)
    total = len(cases)
    if total != 100:
        errors.append(f"expected 100 total cases, got {total}")

    for ctype, expected in TARGET_COUNTS.items():
        got = counts.get(ctype, 0)
        if got != expected:
            errors.append(f"case type {ctype}: expected {expected}, got {got}")
    return errors


def check_overlap(dev: list[dict], test: list[dict]) -> list[str]:
    errors: list[str] = []

    dev_tasks = {c["task"]["task_id"] for c in dev}
    test_tasks = {c["task"]["task_id"] for c in test}
    shared_tasks = dev_tasks & test_tasks
    if shared_tasks:
        errors.append(f"shared task IDs across dev/test: {sorted(shared_tasks)}")

    def norm(q: str) -> str:
        return " ".join(q.lower().split())

    dev_questions = {norm(c["task"]["input"]) for c in dev}
    test_questions = {norm(c["task"]["input"]) for c in test}
    shared_q = dev_questions & test_questions
    if shared_q:
        errors.append(f"shared questions across dev/test: {sorted(shared_q)[:5]}")

    dev_gold = [frozenset(c["gold_candidate_ids"]) for c in dev]
    test_gold = [frozenset(c["gold_candidate_ids"]) for c in test]
    shared_gold = set(dev_gold) & set(test_gold)
    if shared_gold:
        errors.append(f"identical gold passage sets across dev/test: {shared_gold}")

    # Near-duplicate gold passage sets (Jaccard > 0.8).
    near_dupes: list[str] = []
    for i, dg in enumerate(dev_gold):
        for j, tg in enumerate(test_gold):
            union = dg | tg
            if not union:
                continue
            jaccard = len(dg & tg) / len(union)
            if jaccard > 0.8:
                near_dupes.append((dev[i]["case_id"], test[j]["case_id"], round(jaccard, 2)))
    if near_dupes:
        errors.append(f"near-duplicate gold sets (Jaccard>0.8): {near_dupes}")

    return errors


def main() -> int:
    dev = load_jsonl(DEV_PATH)
    test = load_jsonl(TEST_PATH)

    errors: list[str] = []
    errors += validate_cases(dev)
    errors += validate_cases(test)
    errors += check_distribution(dev + test)
    errors += check_overlap(dev, test)

    print(f"dev cases: {len(dev)}")
    print(f"test cases: {len(test)}")
    print(f"combined distribution: {dict(distribution(dev + test))}")
    print(f"dev distribution: {dict(distribution(dev))}")
    print(f"test distribution: {dict(distribution(test))}")

    if errors:
        print("\nFAILED:")
        for e in errors:
            print(f"  - {e}")
        return 1

    print("\nOK: all validation checks passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
