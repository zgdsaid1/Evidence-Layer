# Phase 5A: Held-Out Test Evaluation Plan

## Status and scope

This document freezes one planned evaluation of the held-out test split. It is
a plan only: no test records or labels have been read for this plan, and no
held-out evaluation or provider request has been run. The evaluation is
descriptive and comparative; it is not a deployment decision.

The run will use every record in `data/test/cases.jsonl` exactly once, and
every candidate in each record. It will compare the existing lexical scorer
with Jev relevance scores. The test split will not be used to tune, select,
calibrate, or otherwise change either scorer or its configuration.

## Frozen configuration

- **Lexical:** Existing `LexicalScorer` implementation with its default
  stopword set and token pattern; no constructor overrides.
- **Jev:** Existing optional Jev integration and its fixed batched request
  behavior. Query and candidate text go only in the request state. Create one
  fixed Noul question per candidate, using the same instruction template as the
  completed dev78 run: `Does <candidate_id> contain useful evidence needed to
  answer the task query?` Do not put query or candidate text in instructions.
- **Requested model:** `jev-latest`. Record the actual provider-returned model
  separately on each request.
- **Timeout:** 10 seconds per request.
- **Retry:** `None`; no retries.
- **Request unit:** Exactly one batched `system_one()` request per test record,
  with all candidates for that record in state and one question per candidate.
- **Failure handling:** Stop immediately on the first provider or response
  failure. Do not retry or continue with later records. Do not report a
  complete-run primary metric or comparison if the run is incomplete.
- **Ranking ties:** Sort scores descending; break ties by `candidate_id`
  ascending, matching the existing selector's deterministic tie behavior.
- No prompt, threshold, scorer, or calibration changes are permitted after this
  plan is frozen. There will be no post-hoc model selection.

## Primary metric: macro mean average precision

The single primary metric is **mean average precision (MAP) over records**,
using candidate relevance labels already represented by the schema:
candidate `c` is relevant for a record exactly when its `candidate_id` is in
that record's `gold_candidate_ids`.

For each record, rank all candidates by scorer score using the frozen tie
behavior. At each rank `k` containing a relevant candidate, compute precision
at that rank:

`P@k = (number of relevant candidates in the first k positions) / k`

The record's average precision is the mean of those `P@k` values over all
relevant candidates in that record. MAP is the arithmetic mean of the
record-level average precision values, giving each record equal weight. It
measures how well each scorer ranks the complete candidate set by the existing
gold-evidence labels, without choosing a score threshold or a cutoff `k`.

## Secondary metrics

Only these two secondary metric groups will be reported:

1. **Record-level MRR over the full candidate ranking:** reciprocal rank of
   the first gold candidate, averaged over records. This is an existing
   project metric and requires no tuned cutoff when the complete candidate
   ranking is used.
2. **Operational usage and latency:** request-level input and output token
   totals and cost estimate, plus latency per batched request and aggregate
   mean, median, nearest-rank p95, minimum, and maximum. Count token and latency
   metadata once per request, not once per candidate row. Cost is an estimate,
   not an invoice.

No score threshold, calibration curve, or threshold-dependent diagnostic will
be used to make the comparison.

## Test protocol and validation

1. Before opening the test file, freeze this plan, the code revision, and the
   run configuration above. Record the Git commit SHA, SDK version, UTC
   timestamp, and requested model.
2. Then read and schema-validate every record in `data/test/cases.jsonl`
   exactly once. Do not inspect labels to change the frozen plan or
   configuration.
3. Before any provider request, validate the full file structurally:
   required schema fields and types are valid; record, task, and candidate IDs
   are valid and unique in their applicable scopes; every gold candidate ID
   refers to a candidate in the same record; and every record has at least one
   gold candidate so average precision is defined. If any validation fails,
   stop before making provider requests and report only an aggregate error
   category/count, without identifiers or record contents.
4. For each valid record, compute lexical scores using the frozen default
   scorer and compute Jev scores for every candidate using exactly one
   batched request. Preserve `case_id` as `record_id`, `task.task_id` as
   `question_id`, and each `candidate_id` exactly in the restricted
   machine-readable output.
5. Record candidate-level lexical and Jev scores. Store model requested and
   returned per request/candidate row, and store request-level tokens and
   latency consistently for that record. Measure latency directly around
   `client.system_one()` with `time.perf_counter()`.
6. If any request fails or returns malformed/missing scores, stop immediately,
   do not retry, and mark the run incomplete. Do not calculate or publish a
   full-test primary metric from a partial run.
7. Write aggregate metrics separately from restricted per-candidate rows.
   Never include raw request or response bodies, evidence text, query text,
   source URLs, headers, secrets, or stack traces in reports or logs.

## Statistical reporting

Report point estimates for both scorers and the paired difference
`MAP_Jev - MAP_lexical`. Compute percentile 95% confidence intervals using a
paired record-level bootstrap: resample whole test records with replacement,
keeping each record's two scorer outcomes paired; use 10,000 replicates and
fixed random seed `20261006`. Report the same point estimates and paired
confidence intervals for secondary MRR. Do not bootstrap candidates
independently, because candidates within a record are not independent
evaluation units.

The confidence intervals describe sampling uncertainty under this evaluation
design; they do not establish causality or generalize automatically to other
data distributions.

## Predeclared decision rules

Let `delta` be `MAP_Jev - MAP_lexical`, with its paired, record-bootstrap 95%
confidence interval. Define a practically meaningful difference in advance as
an absolute MAP difference of **0.02**.

- **Jev outperforms lexical:** the entire 95% confidence interval for `delta`
  is greater than `+0.02`.
- **No meaningful difference:** the entire 95% confidence interval lies within
  `[-0.02, +0.02]`.
- **Jev underperforms lexical:** the entire 95% confidence interval for `delta`
  is less than `-0.02`.
- **Inconclusive:** any other confidence-interval result. Do not resolve an
  inconclusive result by changing thresholds, prompts, models, or metrics on
  the test data.

If any provider request fails, stop immediately without retrying; label the
run incomplete, report the completed request count and a sanitized failure
category, and make no comparative decision. If labels or schema are
inconsistent, stop before provider calls, report only sanitized aggregate
validation counts, and make no comparative decision.

## Safety, provenance, and interpretation

- Keep test data local except for the approved batched Jev request. Never send
  source URLs, repository material, or unrelated/private content.
- Do not print, log, store, or expose the API key. Do not log request/response
  bodies, headers, raw provider exceptions, or stack traces.
- Record Git commit SHA, installed SDK version (from local package metadata),
  UTC timestamp, requested model, and returned model when available.
- Ensure reports contain no query or evidence text, source URLs, credentials,
  raw payloads, headers, or stack traces.
- Report the test results as one held-out evaluation only. Do not claim
  production readiness, savings, deployment approval, or causal superiority
  from this single observational run.
- Do not run the evaluation until this plan and configuration are frozen.
