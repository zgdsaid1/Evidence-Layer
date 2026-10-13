# ADR 0001: Keep lexical scorer as default; keep Jev optional

## Status
Accepted

Historical supersession note

ADR 0002 supersedes this decision as current architecture guidance. This ADR remains the historical record of the lexical-default/JEV-optional decision accepted at the time and the evaluation context and evidence supporting it.

## Context

- The Evidence Layer ranks candidate evidence for a task query.
- `LexicalScorer` is deterministic, local, dependency-free, and uses cosine
  similarity over filtered term frequencies.
- `JevEvidenceScorer` is an optional TypeSafe/Jev integration.
- A single held-out test run used 22 records, 110 candidates, and 22
  successful batched `system_one` requests.
- The requested model was `jev-latest`; the returned model was `jev-1.13.0`.
- The predeclared primary metric was macro mean average precision (MAP).
- The predeclared meaningful MAP difference was 0.02.
- The result was **Inconclusive**.

## Decision

Keep `LexicalScorer` as the default evidence scorer. Keep `JevEvidenceScorer`
as an optional integration. Do not make Jev the default without a new,
predeclared evaluation demonstrating a decision-relevant need and benefit.

## Rationale

- The held-out MAP difference was +0.0189 in favor of Jev, below the
  predeclared 0.02 meaningful-effect threshold.
- The paired bootstrap 95% confidence interval for the MAP difference was
  [-0.0152, +0.0644] and included zero.
- Lexical scoring is local, deterministic, dependency-free, and avoids
  provider latency, network failure, and external data transfer.
- The favorable full-ranking MRR result is secondary evidence and does not
  override the frozen primary-metric decision rule.
- The single test run does not establish production readiness, causal
  superiority, savings, or generalization.

## Consequences

- Lexical remains the default path.
- Jev remains available for explicit, optional use.
- Any future Jev adoption requires a new representative evaluation set and a
  frozen protocol before execution.
- Do not retune prompts, thresholds, calibration, or model selection against
  the already-observed held-out split.
- Do not repeatedly rerun evaluation on the same held-out split to obtain a
  favorable result.
- Do not claim production readiness, savings, or superiority from the
  existing single run.

## Evaluation evidence

- Primary metric: macro MAP.
- Lexical MAP: 0.9735.
- Jev MAP: 0.9924.
- Paired MAP difference: +0.0189.
- MAP difference 95% CI: [-0.0152, +0.0644].
- Predeclared decision: Inconclusive.
- Secondary full-ranking MRR: lexical 0.9773; Jev 1.0000.
- Operational latency in the single run: mean 211.68 ms; p95 265 ms.
- Estimated input cost: $0.00065163, an estimate from vendor-published
  pricing; not an invoice.

## References

- [docs/phase5a_heldout_test_evaluation_plan.md](../phase5a_heldout_test_evaluation_plan.md)
- [reports/phase5b_heldout_test_single_run.json](../../reports/phase5b_heldout_test_single_run.json)
