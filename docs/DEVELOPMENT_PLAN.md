# Evidence Layer Development Plan

This is the living development roadmap for the intended Evidence Layer SaaS.
It distinguishes the implementation currently in this repository from the
approved product direction. Planned infrastructure and product features below
are not yet implemented or deployed.

## Current Status

- **Scientific/evaluation core is implemented:** provider-agnostic schemas,
  deterministic lexical scoring, candidate selection, evaluation metrics and
  harness, dataset validation, and an optional Jev scorer.
- **Lexical is the default scorer.** The committed single held-out run measured
  lexical MAP **0.9735** and Jev MAP **0.9924**. The paired MAP difference was
  **+0.0189**, with 95% CI **[−0.0152, +0.0644]**. The predeclared decision was
  **Inconclusive**. See the [Phase 5A plan](phase5a_heldout_test_evaluation_plan.md)
  and [Phase 5B report](../reports/phase5b_heldout_test_single_run.json).
- **Jev is optional, not the default.** The requested model is `jev-latest`;
  it is an alias and the recorded run returned `jev-1.13.0`.
- **Product layer is absent:** no MCP server, database, frontend/dashboard,
  billing, or production connectors exist in this repository.
- **Current branch:** `phase1/evidence-layer-foundation`.

The test result is one evaluation on this project's held-out dataset. It is not
evidence of production readiness, savings, or generalization to customer
workloads.

## Approved Target Architecture

This is the intended architecture, not infrastructure already present in the
repository:

- **Vercel:** Frontend implemented with a Next.js dashboard.
- **Supabase:** Backend services using Postgres, pgvector, Auth, and Edge
  Functions.
- **Railway:** Persistent MCP server process only.
- **Jev:** Optional TypeSafe-backed scoring layer, isolated behind a scorer
  boundary.
- **Lexical:** Always the default and the fallback when Jev is disabled or
  unavailable.

See [Architecture](ARCHITECTURE.md) for boundaries and the planned request
flow.

## Product Goal

The goal is an integrated SaaS product, not only a Python library. The Python
core remains useful as the local evaluation and scoring foundation, while the
product adds a hosted MCP entry point, durable document storage, an initial
connector, usage controls, billing, and an A/B comparison experience.

## Revised Phases

### Phase 1 — MCP server and real retrieval

- Implement a persistent MCP server on Railway.
- Expose `find_evidence` as the initial tool.
- Add a real retrieval pipeline that uses the existing lexical scorer; do not
  rebuild the lexical scorer.
- Permit optional Jev reranking/scoring, retaining lexical as the default and
  always-available fallback.
- Keep request validation, safe errors, and provider-independent core
  interfaces.

### Phase 2 — Supabase and Google Drive

- Integrate Supabase Postgres, pgvector, Auth, and Edge Functions according to
  the target architecture.
- Store document and chunk records and track usage.
- Add the Google Drive connector as the first real source connector.
- Define ingestion, update, deletion, access-control, and provenance behavior
  before enabling customer data flows.

### Phase 3 — Plans and billing

- Add Free and Pro usage entitlements and enforce them server-side.
- Integrate Stripe subscriptions and billing lifecycle events.
- Add $5 credit packs with clear, auditable consumption rules.
- Do not treat estimates of model cost as customer invoices or margin proof.

### Phase 4 — Comparison Lab and beta

- Add a Comparison Lab with a controlled “Run A/B” experience.
- Show scorer outcomes and operational usage with explicit experimental
  limitations.
- Prepare and run a bounded beta only after privacy, reliability, billing,
  support, and rollback requirements are met.

## MVP Scope

### In scope

- MCP server with a `find_evidence` tool.
- Real retrieval using lexical scoring and optional Jev.
- Supabase storage for documents, chunks, and usage tracking.
- Google Drive connector.
- Free plan: **500 requests** and **200K Jev tokens**.
- Pro plan: **$19/month**, **3,000 requests**, and **2M Jev tokens**.
- Stripe billing and **$5 credit packs**.
- Comparison Lab with “Run A/B”.

Plan quota values are product requirements, not current implemented limits.
Their billing period, overage behavior, token accounting, and credit
consumption semantics must be specified before implementation.

### Out of scope

- BYOK.
- Multi-agent orchestration.
- SSO and advanced RBAC.
- Enterprise SLA.
- Notion connector.
- Public general-purpose REST API.

## Success Metrics

These are target outcomes, not measured results:

- Free-to-paid conversion: **3–5%**.
- LLM token reduction: **40–60%**.
- Gross margin: **70%+ within 6–12 months**.

Define denominators, cohorts, measurement windows, excluded traffic, and
instrumentation before using these targets to judge a launch.

## Risks and Mitigations

- **Jev API changes:** isolate the integration behind an abstraction, test the
  optional boundary, and preserve lexical fallback.
- **Scope creep:** keep the explicit MVP and out-of-scope lists current; require
  a deliberate scope decision for additions.
- **Product scope ambiguity:** treat the intended outcome as an integrated
  SaaS product, not a Python library alone, while keeping the present
  repository state accurately described.
- **Unproven value or economics:** do not infer customer benefit, savings, or
  margin from the existing small benchmark; measure on representative,
  privacy-approved workloads.
- **External data and identity risks:** design tenant isolation, connector
  permissions, deletion, retention, and auditability before storing customer
  content.

## Open Decisions

- Use **Meilisearch** or **Postgres full-text search** for lexical retrieval?
- Launch the beta **without billing** or **with billing**?
- Define request quota periods, Jev-token metering, overage behavior, and
  $5-credit-pack consumption.
- Define the Comparison Lab experiment semantics and safe handling of
  customer-provided content.

Resolve these decisions before the affected phase begins; do not silently
assume an implementation choice.
