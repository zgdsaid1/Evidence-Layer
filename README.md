# Evidence Layer

A provider-agnostic **evidence-selection and context-reduction layer** that sits
between an AI agent, its retrieval/RAG system, and a large language model.

The layer receives a **task** and a set of **candidate evidence passages**, then
selects the smallest reliable evidence set, reduces context size, and recommends
whether the agent should **answer**, **abstain**, or **escalate**.

> This is **Phase 1**: the general foundation plus a reproducible evaluation
> dataset. It is a *separate, independent project* (not EMORA).

## Current Status

The repository contains a tested Python evidence-ranking and evaluation core:
schemas, a deterministic lexical scorer, an optional Jev scorer, and a
held-out evaluation artifact. The held-out comparison was **Inconclusive**;
lexical remains the default.

The SaaS product layer is not implemented: there is no MCP server, database,
frontend/dashboard, billing, or real source connector. The planned target
architecture is Vercel/Next.js for the frontend, Supabase for backend services,
Railway for the persistent MCP server, and Jev through the optional TypeSafe
integration. This is a target design, not a description of deployed services.

See the living [Development Plan](docs/DEVELOPMENT_PLAN.md),
[Product Requirements (PRD)](docs/PRD.md), and
[Architecture](docs/ARCHITECTURE.md).

---

## 1. Vision

Agents increasingly work over large, messy retrieved context. Passing everything
to a model is expensive and unreliable; cutting too aggressively drops the
evidence the answer actually needs. Evidence Layer is the narrow middle: a
domain-agnostic core that decides *what evidence is required, what can be
dropped, and when the system should not answer at all*.

Future target domains include (not implemented yet):

- customer support tickets
- coding agents / vibe-coding workflows
- compliance and internal policy checks
- contracts and procurement
- enterprise knowledge search
- research and academic evidence
- invoices and procurement matching

Phase 1 builds only the **general core** and **adapter interfaces**, and starts
with one domain: **technical documentation / RAG evidence**.

## 2. Phase 1 scope and strict non-goals

**In scope (this phase):**

- Domain-agnostic Pydantic v2 schemas
- An adapter interface (`normalize_task`, `normalize_candidates`,
  `apply_policy`, `interpret_result`)
- One no-op adapter (`DocumentationRAGAdapter`)
- A reproducible evaluation dataset built from real public documentation
- A validation script and a unit-test suite

**Out of scope (explicitly not built, by rule):**

- No Jev, rerankers, or LLM calls in the Phase 1 default core (an optional,
  separately installed Jev scorer/evaluation path was added in later phases; it
  may call an external paid API and is never required)
- No connectors; no cost calculation in the default core
- No SaaS dashboard, no deployment
- No API keys, secrets, or `.env` files
- No paid model APIs (OpenAI, Anthropic, Cohere, Voyage, ...)
- No integrations for Zendesk, Intercom, Freshdesk, GitHub, Slack, Notion

## 3. Documentation source and licensing

**Chosen source: the official PostgreSQL documentation**
(https://www.postgresql.org/docs/current/).

Why:

- **Stable public availability** — the docs are served at stable URLs
  (`/docs/current/<page>.html`) with per-section anchors, and are versioned.
- **Clear, permissive licensing** — published under the *PostgreSQL License*, a
  liberal open-source license comparable to MIT/BSD. It permits use, copying,
  modification, and distribution with retention of the copyright notice.
- **Technical, factual content** — ideal for measuring "did the layer keep the
  evidence that actually answers the question."

The quoted passages are attributed in `data/corpus/NOTICE.md`
(Copyright © 1996-2026 The PostgreSQL Global Development Group). This project
is not affiliated with the PostgreSQL Global Development Group.

## 4. Repository structure

```
Evidence-Layer/
├── LICENSE
├── README.md
├── pyproject.toml
├── .gitignore
├── src/
│   └── evidence_layer/
│       ├── __init__.py
│       ├── schemas.py
│       └── adapters/
│           ├── __init__.py
│           ├── base.py
│           └── documentation_rag.py
├── data/
│   ├── corpus/
│   │   ├── NOTICE.md
│   │   └── postgresql_passages.jsonl      # 62 quoted passages
│   ├── dev/
│   │   └── cases.jsonl                    # generated (78 cases)
│   └── test/
│       └── cases.jsonl                    # generated (22 cases)
├── scripts/
│   ├── build_dataset.py                   # reproducible dataset generator
│   └── validate_dataset.py                # integrity checks
└── tests/
    ├── conftest.py
    ├── test_schemas.py
    ├── test_adapter.py
    └── test_dataset.py
```

## 5. Data model (`src/evidence_layer/schemas.py`)

All schemas are Pydantic v2 models with `extra="forbid"` and strict enums.

| Model | Key fields |
|---|---|
| `Task` | `task_id`, `task_type`, `domain`, `input`, `language`, `metadata` |
| `EvidenceCandidate` | `candidate_id`, `source_id`, `source_url`, `text`, `metadata` |
| `Policy` | `context_budget_tokens`, `min_evidence`, `max_evidence`, `languages`, `abstain_when_uncertain`, `policy_version` |
| `EvidenceSelectionRequest` | `request_id`, `task`, `candidates`, `policy` |
| `EvidenceSelectionResult` | `request_id`, `task_id`, `selected_candidate_ids`, `rejected_candidate_ids`, `decision`, `reason_codes`, `context_tokens_before`, `context_tokens_after`, `policy_version` |
| `EvaluationCase` | `case_id`, `case_type`, `task`, `candidates`, `gold_candidate_ids`, `required_facts`, `source_urls`, `untrusted_candidate_ids` |

Enums:

- `task_type`: `support_ticket`, `coding_task`, `compliance_check`,
  `contract_review`, `knowledge_query`, `research`, `custom`
- `decision`: `answer_with_context`, `abstain`, `escalate_for_review`,
  `insufficient_evidence`
- `case_type`: `direct_factual`, `multi_source`, `false_premise`,
  `ambiguous`, `prompt_injection`

## 6. Adapter interface and no-op adapter

`EvidenceAdapter` (in `adapters/base.py`) is an abstract base class with four
methods every future domain adapter must implement:

- `normalize_task(raw) -> Task`
- `normalize_candidates(raw) -> list[EvidenceCandidate]`
- `apply_policy(task, candidates, policy) -> EvidenceSelectionResult`
- `interpret_result(result) -> dict`

`DocumentationRAGAdapter` is the initial **no-op** implementation. Its
`apply_policy` is a deterministic *greedy first-N within budget* baseline using a
naive whitespace token estimate. It does **not** rank, rerank, or call any model
— it exists to smoke-test the pipeline, not to claim quality.

## 7. The evaluation dataset

### How it is built

The dataset is generated deterministically by `scripts/build_dataset.py` from two
committed inputs:

1. `data/corpus/postgresql_passages.jsonl` — **62 passages** quoted from the
   PostgreSQL docs.
2. **100 hand-authored question specs** inside the build script, each with a
   question, one or more gold passage IDs, and required facts.

For each question the builder assembles a **simulated retrieval**: the gold
passage(s) plus same-topic distractor passages (5 candidates per case), and for
prompt-injection cases one extra **untrusted** candidate. The dev/test split uses
union-find so that no gold passage set (and therefore no near-duplicate passage
set) spans both sets.

### Case-type distribution (target vs. actual)

| case_type | target | count |
|---|---:|---:|
| direct_factual | 40% | 40 |
| multi_source | 25% | 25 |
| false_premise | 15% | 15 |
| ambiguous | 10% | 10 |
| prompt_injection | 10% | 10 |
| **total** | 100% | **100** |

Split: **78 dev** / **22 test** (stratified, with passage-overlap closure).

### Sample records

`direct_factual` case (abridged):

```json
{
  "case_id": "case_0007",
  "case_type": "direct_factual",
  "task": {
    "task_id": "task_0007",
    "task_type": "knowledge_query",
    "domain": "technical_documentation",
    "input": "How does `character(n)` differ from `character varying(n)` for strings shorter than n?",
    "language": "en"
  },
  "candidates": [
    {"candidate_id": "pg_char_padding", "source_url": "https://www.postgresql.org/docs/current/datatype-character.html", "text": "If the string to be stored is shorter than the declared length, values of type character will be space-padded; values of type character varying will simply store the shorter string."}
  ],
  "gold_candidate_ids": ["pg_char_padding"],
  "required_facts": ["character is space-padded", "character varying stores the shorter string"],
  "source_urls": ["https://www.postgresql.org/docs/current/datatype-character.html"],
  "untrusted_candidate_ids": []
}
```

`prompt_injection` case (abridged): the query embeds an injection attempt, an
`untrusted_candidate_ids` entry is present, and the gold IDs point only at the
legitimate documentation passage.

## 8. Running it

Requires Python 3.12+ (tested on 3.14). Dependencies: `pydantic>=2` and
`pytest`.

```bash
# (optional) create a venv
python3 -m venv .venv && source .venv/bin/activate

# install in editable mode + dev deps
pip install -e ".[dev]"

# regenerate the dataset
python scripts/build_dataset.py

# validate the dataset (exit code 0 = pass)
python scripts/validate_dataset.py

# run the tests
pytest
```

Expected test result: all tests pass (schemas, adapter interface, dataset
integrity, evaluation, scorers). The count grows as tests are added.

## 9. Regenerating and extending

- **Regenerate**: `python scripts/build_dataset.py` rewrites `data/dev` and
  `data/test` from the committed corpus + specs, deterministically.
- **Add a passage**: append a line to `data/corpus/postgresql_passages.jsonl`.
- **Add a question**: append an `S(...)` entry to `SPECS` in
  `scripts/build_dataset.py`, following the existing `type`/`gold`/`facts`
  shape, then re-run the build and validation scripts.
- **Add a domain**: implement a new subclass of `EvidenceAdapter` in
  `src/evidence_layer/adapters/` and register it in `adapters/__init__.py`.

## 10. What this dataset does and does not prove

**It provides:** a reproducible, schema-valid, split-safe foundation for later
measuring whether an evidence-selection policy can reduce context while keeping
the evidence that answers each question.

**It does NOT prove:** product-market fit, cost savings, model-quality
improvement, or that any particular selection algorithm works. There is no
real retriever, no reranker, and no LLM involved yet. Retrieval is simulated,
and the "gold" labels are hand-written against the documentation.

## 11. Future adapters and integrations (not built yet)

- A real `DocumentationRAGAdapter` selection policy (reranking/scoring) behind
  the same interface.
- Domain adapters for the target domains listed in §1.
- Connectors and cost accounting (both explicitly deferred).
- A held-out scoring harness that grades a selector against
  `gold_candidate_ids` + `required_facts`.

## 12. Assumptions

- A fixed candidate count (5) and a single docs source are acceptable for a
  first evaluation foundation.
- "Token" counts in the no-op adapter are a word-count heuristic, not a real
  tokenizer (no model/tokenizer is called by rule).
- The dev/test split may have a slightly uneven per-split type mix; the
  *overall* distribution is exact, and cross-set passage overlap is forbidden.

## 13. Unresolved questions

- How to grade *partial* correctness (a selector that keeps the gold passage
  plus one distractor) versus exact-match.
- Whether `abstain` / `escalate_for_review` / `insufficient_evidence` decisions
  can be meaningfully evaluated from this dataset without an LLM judge.
- How to source a *real* retriever's candidate rankings (rather than simulated
  retrieval) without calling any paid API.
- The right near-duplicate threshold (Jaccard) for "near-duplicate passage set".

## 14. Next milestone (smallest)

Wire a **second, non-trivial selection policy** behind `apply_policy` for
`DocumentationRAGAdapter` (e.g., lexical/keyword overlap scoring against the
task — still no LLM/reranker) and add a scoring harness that reports
recall@k and context-reduction versus the current no-op baseline.

---

## 15. Claims

**VERIFIED FACT**

- The repository contains 62 quoted PostgreSQL-documentation passages
  (`data/corpus/postgresql_passages.jsonl`), each with a `source_url`.
- The dataset contains 100 cases with the exact distribution
  40/25/15/10/10 across `direct_factual` / `multi_source` / `false_premise` /
  `ambiguous` / `prompt_injection`.
- `scripts/validate_dataset.py` passes (exit 0), confirming schema validity,
  unique task IDs, non-empty queries/passages, valid gold IDs, required facts,
  distribution, and no dev/test overlap.
- `pytest` passes with no failures.
- The default local core makes no paid model API, Jev, reranker, or LLM call
  and has no connector, secret, `.env`, or deployment. The optional Jev
  integration (not installed by default) may call an external API.

**PROPOSAL**

- PostgreSQL documentation is a suitable first source because it is stable,
  permissively licensed, and factual; Supabase / Stripe / LangChain could serve
  as later domains.
- The simulated-retrieval design (gold + same-topic distractors + untrusted
  candidates) is a reasonable proxy for a real retriever for a Phase-1
  foundation.

**UNRESOLVED QUESTION**

- Whether this dataset, once scored, will show that context reduction can
  preserve answer quality — that is exactly what it is designed to test later,
  and no claim is made about the outcome now.

---

## 16. Phase 2 — local lexical baseline and evaluation harness

Phase 2 adds a **local, deterministic lexical baseline** and a metrics harness.
It is **not** semantic retrieval, Jev, a reranker, an LLM, a security audit, or a
product benchmark. It measures word-overlap evidence selection on the Phase 1
dataset and reports evidence-retention / context-reduction metrics.

### Components

- `LexicalScorer` (`src/evidence_layer/scoring/lexical.py`) — standard-library
  only, no network access. Lower-cases, tokenizes on `[a-z0-9]+`, drops a small
  fixed English stopword list, and scores with cosine similarity of raw
  term-frequency vectors. Deterministic for a fixed input.
- `Scorer` (`src/evidence_layer/scoring/base.py`) — the interface a future Jev /
  reranker / provider scorer can implement.
- `select_top_k` (`src/evidence_layer/selection.py`) — returns the top-k
  candidate IDs by score (ties broken by `candidate_id` ascending). `k` is
  configurable and validated: it must be an integer ≥ 1, otherwise it fails
  with a clear `ValueError` / `TypeError`.
- Harness (`scripts/run_evaluation.py`) — runs K = 1, 3, 5 on the development
  and held-out test sets independently and writes `reports/baseline_dev.json`,
  `reports/baseline_test.json`, and `reports/baseline_cases.csv`.

### Metric definitions

- `recall@k` = |gold ∩ selected| / |gold|
- `precision@k` = |gold ∩ selected| / |selected|
- `mean_selected_evidence_count` = mean number of selected candidates per case
- `estimated_context_units` = whitespace word count (explicitly NOT a token
  count; no tokenizer is used)
- `context_reduction_ratio` = 1 − selected_units / all_candidate_units
- `failure_count` = number of cases where no gold evidence was selected

### How to run

```bash
python scripts/build_dataset.py     # regenerate dataset
python scripts/validate_dataset.py  # validate dataset
python scripts/run_evaluation.py    # generate baseline reports
pytest                              # run all tests
```

### Limitations

- Lexical overlap only: it does not understand meaning, negation, or
  instruction injection. Prompt-injection cases are *measured*, not "handled".
- `estimated_context_units` is a whitespace word-count heuristic, not a real
  tokenizer or cost estimate.
- The held-out test set is used for reporting only; the algorithm was not tuned
  on it.
- The scorer is a *baseline*; it makes no claim of retrieval quality, cost
  savings, security, or compliance.

---

## 17. Phase 2A — baseline fairness, split audit, and sensitivity analysis

Phase 2A audits the existing lexical baseline **before committing it**, without
changing the dataset or the corpus.

### New ranking metrics

Added to every K=1/3/5 evaluation:

- `mrr_at_k` — reciprocal rank of the first selected gold candidate
  (0.0 if none selected).
- `any_evidence_hit_rate@K` — fraction of cases with **at least one** selected
  gold candidate.
- `full_evidence_rate@K` — fraction of cases where **all** gold candidates are
  selected.

`any_evidence_hit_rate` answers "did we keep *something* relevant?", while
`full_evidence_rate` answers "did we keep *everything* required?". For an
individual case, full evidence is 0 when the selected K cannot contain all of
that case's gold evidence IDs; the aggregate `full_evidence_rate` can still be
above 0 because some cases have one or fewer gold evidence IDs.

### Split audit

`scripts/run_split_audit.py` writes `reports/split_audit.json` and
`reports/split_audit.md`. It is **read-only**: it compares development vs
held-out test on case-type counts, gold/candidate counts, query and candidate
word counts, query→gold vs query→distractor lexical overlap (stopword-agnostic
token Jaccard), duplicate/near-duplicate query indicators, and repeated
question-template indicators. It does not move cases or alter anything.

### Stopword sensitivity

The named baseline is **`lexical_stopword_filtered`** (`LexicalScorer`). A single
comparison variant **`lexical_no_stopword_filter`** (`LexicalNoStopwordScorer`)
uses the same tokenization and cosine formula but retains stopwords.

`scripts/run_sensitivity.py` evaluates both variants **on the development split
only** and writes `reports/sensitivity_dev.json` and
`reports/sensitivity_dev.csv`. This is for interpretation, not selection: the
held-out test set is **never used to tune the scorer**, and the no-stopword
variant does not become the default automatically.

### How to run

```bash
python scripts/build_dataset.py     # regenerate dataset
python scripts/validate_dataset.py  # validate dataset
python scripts/run_evaluation.py    # baseline reports (incl. new ranking metrics)
python scripts/run_split_audit.py   # split audit (JSON + Markdown)
python scripts/run_sensitivity.py   # stopword sensitivity (dev only)
pytest                              # run all tests
```

## 18. Optional Jev scorer

The Jev scorer is an optional integration available through `pip install
.[jev]` (`typesafe-sdk==0.7.2`). The SDK version is pinned; the requested model
defaults to `jev-latest` because that alias was available to the account
verified during development. It is an alias and may resolve to a changing
underlying model; this does not provide pinned-model reproducibility. Callers
can select another model explicitly with `JevEvidenceScorer(model="...")`.

The default project installation does not import or require the TypeSafe SDK.
Unit tests use fake clients. Future run metadata records the requested model,
the actual `response.model` when safely available, the locally installed SDK
version, a UTC timestamp, and the Git commit SHA when available. It does not
claim production readiness or benchmark results. Input-cost estimates, when
available from provider-reported token usage, are estimates from
vendor-published pricing and are not invoices. Retry settings remain
provider-neutral configuration only: SDK retry is disabled until its policy
constructor is verified, and retry counts are not measured or reported by this
integration.
