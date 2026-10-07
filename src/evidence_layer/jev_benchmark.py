"""Configuration-only scaffolding for a future development Jev benchmark."""

from __future__ import annotations

import argparse
import math
from dataclasses import dataclass

from evidence_layer.scoring.jev import DEFAULT_JEV_MODEL, RetryPolicy


@dataclass(frozen=True)
class JevBenchmarkConfig:
    split: str = "dev"
    allow_test: bool = False
    max_cases: int = 10
    max_candidates_per_case: int = 5
    model: str = DEFAULT_JEV_MODEL
    timeout: float = 10.0
    retry_policy: RetryPolicy = RetryPolicy()


def build_benchmark_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Validate future Jev benchmark settings; performs no provider calls."
    )
    parser.add_argument("--split", choices=("dev", "test"), default="dev")
    parser.add_argument("--allow-test", action="store_true")
    parser.add_argument("--max-cases", type=int, default=10)
    parser.add_argument("--max-candidates-per-case", type=int, default=5)
    parser.add_argument("--model", default=DEFAULT_JEV_MODEL)
    parser.add_argument("--timeout", type=float, default=10.0)
    return parser


def parse_benchmark_config(
    args: list[str] | None = None,
) -> JevBenchmarkConfig:
    parser = build_benchmark_parser()
    parsed = parser.parse_args(args)
    if parsed.split == "test" and not parsed.allow_test:
        parser.error("--allow-test is required when --split test is selected")
    if parsed.max_cases < 1:
        parser.error("--max-cases must be at least 1")
    if parsed.max_candidates_per_case < 1:
        parser.error("--max-candidates-per-case must be at least 1")
    if not math.isfinite(parsed.timeout) or parsed.timeout <= 0:
        parser.error("--timeout must be a finite positive number")
    return JevBenchmarkConfig(
        split=parsed.split,
        allow_test=parsed.allow_test,
        max_cases=parsed.max_cases,
        max_candidates_per_case=parsed.max_candidates_per_case,
        model=parsed.model,
        timeout=parsed.timeout,
    )
