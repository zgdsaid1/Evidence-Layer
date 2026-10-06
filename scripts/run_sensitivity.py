#!/usr/bin/env python3
"""Run the stopword sensitivity experiment on the development split only.

Writes ``reports/sensitivity_dev.json`` and ``reports/sensitivity_dev.csv``.
This is a comparison of two named variants; it does NOT tune or select a
winner, and the held-out test set is not touched.
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
from evidence_layer.analysis import (  # noqa: E402
    SENSITIVITY_CSV_FIELDS,
    compute_sensitivity,
    sensitivity_csv_rows,
)
from evidence_layer.evaluation import K_VALUES  # noqa: E402
from evidence_layer.scoring.lexical import (  # noqa: E402
    LexicalNoStopwordScorer,
    LexicalScorer,
)

REPORTS_DIR = ROOT / "reports"


def main() -> None:
    dev, _ = build_dataset.build_cases()
    variants = {
        "lexical_stopword_filtered": LexicalScorer(),
        "lexical_no_stopword_filter": LexicalNoStopwordScorer(),
    }
    sensitivity = compute_sensitivity(dev, variants, K_VALUES)

    report = {
        "split": "dev",
        "k_values": list(K_VALUES),
        "variants": sensitivity,
    }

    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    (REPORTS_DIR / "sensitivity_dev.json").write_text(json.dumps(report, indent=2) + "\n")

    rows = sensitivity_csv_rows(sensitivity, K_VALUES)
    with (REPORTS_DIR / "sensitivity_dev.csv").open("w", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=SENSITIVITY_CSV_FIELDS)
        writer.writeheader()
        writer.writerows(rows)

    print("wrote reports/sensitivity_dev.json and reports/sensitivity_dev.csv")


if __name__ == "__main__":
    main()
