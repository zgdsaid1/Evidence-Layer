#!/usr/bin/env python3
"""Run the local lexical baseline harness on development and held-out test sets.

Writes (regenerable, deterministic):

* ``reports/baseline_dev.json``
* ``reports/baseline_test.json``
* ``reports/baseline_cases.csv``

No network access. Generated reports are gitignored and not committed.
"""

from __future__ import annotations

import csv
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

import build_dataset  # noqa: E402
from evidence_layer.evaluation import (  # noqa: E402
    CSV_FIELDS,
    K_VALUES,
    build_report,
    evaluate_cases,
    to_csv_rows,
)
from evidence_layer.scoring.lexical import LexicalScorer  # noqa: E402

REPORTS_DIR = ROOT / "reports"


def main() -> None:
    scorer = LexicalScorer()
    dev, test = build_dataset.build_cases()

    dev_result = evaluate_cases(dev, scorer, K_VALUES)
    test_result = evaluate_cases(test, scorer, K_VALUES)

    REPORTS_DIR.mkdir(parents=True, exist_ok=True)

    (REPORTS_DIR / "baseline_dev.json").write_text(
        json.dumps(build_report("dev", scorer.name, dev_result), indent=2) + "\n"
    )
    (REPORTS_DIR / "baseline_test.json").write_text(
        json.dumps(build_report("test", scorer.name, test_result), indent=2) + "\n"
    )

    rows = to_csv_rows("dev", dev_result["rows"]) + to_csv_rows("test", test_result["rows"])
    with (REPORTS_DIR / "baseline_cases.csv").open("w", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=CSV_FIELDS)
        writer.writeheader()
        writer.writerows(rows)

    print(f"dev  -> {len(dev_result['rows'])} rows ({len(dev)} cases x {len(K_VALUES)} k)")
    print(f"test -> {len(test_result['rows'])} rows ({len(test)} cases x {len(K_VALUES)} k)")
    print("wrote reports/baseline_dev.json, reports/baseline_test.json, reports/baseline_cases.csv")


if __name__ == "__main__":
    main()
