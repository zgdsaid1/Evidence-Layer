# Evidence Layer Development Plan

This is the living development plan for the intended Evidence Layer SaaS. It
distinguishes current implementation and deployments from the approved product
direction. Future product capabilities are identified separately from what is
already present.

## Current Status

- **Scientific/evaluation core is implemented:** provider-agnostic schemas,
  deterministic lexical scoring and candidate selection, evaluation metrics
  and harness, dataset validation, and a JEV scorer behind provider-selection
  policy.
- **The committed historical held-out run** measured lexical MAP **0.9735** and
  JEV MAP **0.9924**. The paired MAP difference was
  **+0.0189**, with 95% CI **[−0.0152, +0.0644]**. The predeclared decision was
  **Inconclusive**. See the [Phase 5A plan](phase5a_heldout_test_evaluation_plan.md)
  and [Phase 5B report](../reports/phase5b_heldout_test_single_run.json) —
  historical evaluation-phase numbering, unrelated to the ROADMAP's Phase 5.
- **Approved architecture:** JEV is the intended primary evidence-scoring and
  ranking provider only when explicitly enabled and permitted by policy; retain
  the policy gates and whole-request lexical fallback. The historical
  evaluation decision in ADR 0001 is superseded as
  architecture guidance, while its measurements remain historical.
- **A local stdio MCP server is implemented** and exposes `retrieve_evidence`.
  Hosted HTTP MCP, hosted authentication and tenant-isolation enforcement,
  production database/RLS, hosted provider-transfer authorization, SaaS
  dashboard capabilities, billing, production connectors, source router, and
  Decisions API client do not yet exist in this repository. A synthetic-only
  Next.js Evidence Explorer prototype exists at `apps/web/` and its production
  deployment from `main` on Vercel is confirmed; it has no backend integration
  or customer operations. Final answer generation remains with the caller's
  model.

`services/evidence-service/` contains a health-only FastAPI app deployed on
Railway with a `GET /healthz` endpoint. It is separate from the implemented
local MCP stdio server and does not provide hosted authentication, retrieval,
customer operations, or provider integration. A persistent MCP service remains
future work.

`LocalCorpusRetriever` is implemented, but its current default source-read
boundary denies before opening corpus content. The retrieval code is designed
to select candidates with lexical overlap, score and rank them, then apply
`budget_words`, which counts `text.split()` words and is not a token count; the
default-deny boundary currently prevents that path from reading corpus records.
The standard MCP stdio path remains lexical-only and likewise cannot read corpus
content without a future trusted source boundary. Live JEV transfer is
hard-denied on supported package paths, including when dependencies are
injected. The local health-only HTTP service is not the hosted service or a
production retrieval phase.

The test result is one evaluation on this project's held-out dataset. It is not
evidence of production readiness, savings, or generalization to customer
workloads.

## Approved Target Architecture

This is the intended architecture. Current deployments are identified below;
the remaining platform components are not infrastructure already present in
the repository:

- **Vercel:** A synthetic-only Next.js Evidence Explorer prototype is
  implemented and deployed from `main`; SaaS dashboard capabilities remain
  planned.
- **Supabase:** Backend services using Postgres, pgvector, Auth, and Edge
  Functions.
- **Railway:** The health-only Python service is deployed; a persistent MCP
  server remains planned.
- **JEV:** Intended primary TypeSafe-backed evidence-scoring and ranking
  provider only when explicitly enabled and permitted by policy. Before sending
  query or candidate text, the trusted server must separately authorize that
  provider transfer and minimize the data sent. Source access alone does not
  authorize transfer; if authorization is absent or unclear, do not send the
  data.
- **Lexical:** On any JEV failure—including provider errors, timeouts, missing,
  malformed, invalid, or incomplete scores, or results that fail validation—
  recompute the entire candidate set lexically. Never mix JEV and lexical
  scores or rankings.
- **OpenAI Decisions API:** Required routing intelligence for complex source
  routing only. The future router may route simple queries deterministically.
  Filter the trusted source catalog before routing and re-enforce source
  authorization before access. Before transferring query text to Decisions,
  require separate trusted server-side authorization and send only minimum
  query/source metadata, never documents. Router and Decisions cannot add
  sources, grant permissions, bypass tenant boundaries, or authorize transfers.
  Deterministic fallback on unavailable, timed-out, or invalid Decisions output
  may select only safely eligible, authorized sources; if none can be
  established, stop rather than widening access.
- **Evidence output:** Returns selected/ranked evidence, provenance, and
  relevant metadata to the caller.
- **Final answers:** Generated by the caller's model, not by this service.

Delivery phasing follows the canonical [ROADMAP.md](ROADMAP.md): Phase 5
requires mandatory per-user tenant isolation and protection of each user's
data. Phase 6 adds advanced team management, workspaces, broader collaboration,
and billing; it does not defer the Phase 5 isolation requirement. Phase 5 usage
metering and free-tier safety limits are separate from payment collection.

The source router and Decisions API client are planned work, not implemented.
Their separate future scope is authorization-filtered catalog construction,
selective routing policy, minimal metadata serialization, Decisions output
validation, deterministic routing fallback, and isolated fake-based tests.
Keep that scope separate from PR #12's JEV provider-selection policy.

See [Architecture](ARCHITECTURE.md) for boundaries and the planned request
flow.

## Product Goal

The goal is an integrated SaaS product, not only a Python library. The Python
core remains useful as the local evaluation and scoring foundation, while the
product adds a hosted MCP entry point, durable document storage, an initial
connector, usage controls, billing, and an A/B comparison experience.

## Revised Phases

> **Note:** These implementation phases are historical and are superseded by the
> canonical product phases in [ROADMAP.md](ROADMAP.md) (Phase 0–6: local MCP
> foundation, prove value, Comparison Lab, connector contract, Google Drive,
> SaaS beta, billing and expansion). The names below are retained for history;
> new work should reference the ROADMAP phases.

### Phase 1 — MCP server and real retrieval

- A local stdio MCP server exposing `retrieve_evidence` is already implemented.
- Implement the persistent Railway HTTP MCP server.
- Expose `retrieve_evidence` as the initial tool.
- Add a retrieval pipeline using JEV as the primary evidence scorer, retaining
  whole-request lexical fallback under the provider-selection policy.
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
- Define any future credit-pack terms and auditable consumption rules before
  implementation; no amount is approved.
- Do not treat estimates of model cost as customer invoices or margin proof.

### Phase 4 — Comparison Lab and beta

- Add a Comparison Lab with a controlled “Run A/B” experience.
- Show scorer outcomes and operational usage with explicit experimental
  limitations.
- Prepare and run a bounded beta only after privacy, reliability, support, and
  rollback requirements are met. Under the canonical roadmap, Phase 5 beta
  precedes Phase 6 billing.

## MVP Scope

### In scope

- MCP server with a `retrieve_evidence` tool.
- Real retrieval using JEV evidence scoring with whole-request lexical fallback.
- Complex source routing through the planned Decisions API router; router
  implementation is not in the current PR scope.
- Supabase storage for documents, chunks, and usage tracking.
- Google Drive connector.
- Phase 5 usage metering and safety limits; no numeric quota values or periods
  are approved. Usage limits and metering do not imply payment collection.
- Comparison Lab with “Run A/B”.

No numeric plan quota values are approved or implemented. Billing periods,
overage behavior, token accounting, and credit consumption semantics remain
open product decisions.

Paid Pro, Stripe subscription billing, and possible credit packs are Phase 6
targets under the canonical roadmap, outside the Phase 5 beta MVP. Pricing,
amounts, periods, and accounting rules remain open product decisions.

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

- **JEV API changes:** isolate the provider behind the selection policy, test
  failure handling, and preserve whole-request lexical fallback.
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
- Define the selective Decisions routing policy, trusted source metadata, and
  deterministic routing fallback separately from JEV scoring policy.
- Define request quota periods, JEV-token metering, separate Decisions-routing
  cost limits, overage behavior, and $5-credit-pack consumption.
- Define the Comparison Lab experiment semantics and safe handling of
  customer-provided content.

Resolve these decisions before the affected phase begins; do not silently
assume an implementation choice.
