# Evidence Layer

A provider-agnostic **evidence-selection and context-reduction layer** that sits
between an AI agent, its retrieval/RAG system, and a large language model.

The layer receives a **task** and a set of **candidate evidence passages**, then
selects the smallest reliable evidence set, reduces context size, and recommends
whether the agent should **answer**, **abstain**, or **escalate**.

> This is **Phase 1**: the general foundation plus a reproducible evaluation
> dataset. It is a *separate, independent project* (not EMORA).

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

- No Jev, rerankers, or LLM calls
- No connectors, no cost calculation
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

Expected test result: **21 passed** (schemas, adapter interface, dataset
integrity).

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
- `pytest` reports 21 passing tests.
- No paid model API, Jev, reranker, LLM call, connector, cost calculation,
  `.env`, secret, or deployment is present in the code.

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

