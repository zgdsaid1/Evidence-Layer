#!/usr/bin/env python3
"""Generate a read-only dev-vs-test split-audit report (JSON + Markdown).

Writes ``reports/split_audit.json`` and ``reports/split_audit.md``. Does not
mutate the dataset, move cases, or use the test set for tuning.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

import build_dataset  # noqa: E402
from evidence_layer.analysis import compute_split_audit  # noqa: E402

REPORTS_DIR = ROOT / "reports"


def _stats_line(name: str, s: dict) -> str:
    return f"- {name}: count={s['count']}, min={s['min']}, max={s['max']}, mean={s['mean']}"


def render_markdown(audit: dict) -> str:
    lines = ["# Split Audit (development vs held-out test)", ""]
    for split in ("dev", "test"):
        d = audit[split]
        lines.append(f"## {split} (n_cases={d['n_cases']})")
        lines.append("")
        lines.append("### case_type counts")
        for ct, n in sorted(d["case_type_counts"].items()):
            lines.append(f"- {ct}: {n}")
        lines.append("")
        lines.append("### shape / lexical statistics")
        lines.append(_stats_line("gold_ids_per_case", d["gold_ids_per_case"]))
        lines.append(_stats_line("candidate_count_per_case", d["candidate_count_per_case"]))
        lines.append(_stats_line("query_word_count", d["query_word_count"]))
        lines.append(_stats_line("candidate_word_count", d["candidate_word_count"]))
        lines.append(_stats_line("query_to_gold_overlap (Jaccard)", d["query_to_gold_overlap"]))
        lines.append(_stats_line("query_to_distractor_overlap (Jaccard)", d["query_to_distractor_overlap"]))
        lines.append("")
        dup = d["duplicate_query_indicators"]
        lines.append("### query wording indicators")
        lines.append(f"- exact_duplicate_query_count: {dup['exact_duplicate_query_count']}")
        lines.append(f"- near_duplicate_query_pairs (Jaccard>0.8): {dup['near_duplicate_query_pairs']}")
        lines.append(f"- repeated_template_count: {d['repeated_template_count']}")
        if d["repeated_templates"]:
            items = ", ".join(f"{k}={v}" for k, v in sorted(d["repeated_templates"].items()))
            lines.append(f"- repeated templates: {items}")
        lines.append("")

    cs = audit["cross_split"]
    lines.append("## cross-split")
    lines.append(f"- exact_duplicate_queries_across_splits: {cs['exact_duplicate_queries_across_splits']}")
    lines.append(f"- near_duplicate_query_pairs_across_splits (Jaccard>0.8): {cs['near_duplicate_query_pairs_across_splits']}")
    lines.append("")
    return "\n".join(lines)


def main() -> None:
    dev, test = build_dataset.build_cases()
    audit = compute_split_audit(dev, test)
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    (REPORTS_DIR / "split_audit.json").write_text(json.dumps(audit, indent=2) + "\n")
    (REPORTS_DIR / "split_audit.md").write_text(render_markdown(audit) + "\n")
    print("wrote reports/split_audit.json and reports/split_audit.md")


if __name__ == "__main__":
    main()
