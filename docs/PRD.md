# Product Requirements Document

## Product Summary

Evidence Layer is intended to be a SaaS evidence-selection service between an
agent or RAG system and the model that will produce an answer. It receives a
task query and candidate passages, ranks evidence, and returns a compact
evidence set with provenance and usage metadata.

**Product intent:** a hosted SaaS product with an MCP interface, not only a
Python library. The current repository is still the Python scoring and
evaluation foundation; this PRD describes the target product.

## Problem

Agents often pass too much retrieved context to a downstream model or remove
useful evidence while reducing it. Evidence Layer should identify which
candidates are useful for the task, reduce irrelevant context where possible,
and make the selection behavior inspectable.

## Users and Use Cases

- An agent developer wants an MCP tool to retrieve/rank evidence for a query.
- A team wants to connect a document source and reuse evidence across agent
  runs.
- A user wants to compare evidence-ranking behavior through a controlled A/B
  workflow.
- An operator needs usage limits and account-level usage visibility.

These are intended user needs; customer discovery and product-market fit are
not established by the repository's evaluation dataset.

## MVP Goals

1. Provide an MCP `retrieve_evidence` tool.
2. Retrieve authorized candidate evidence and use JEV as the intended primary
   evidence scorer only when explicitly enabled and permitted by policy.
3. On any JEV failure or invalid/incomplete result, recompute the entire
   candidate set lexically; never mix JEV and lexical scores or rankings.
4. Store documents, chunks, and usage in Supabase.
5. Connect Google Drive as the first source connector.
6. Enforce Phase 5 free-tier usage limits and metering.
7. Provide a Comparison Lab that runs and presents an A/B comparison.

The Phase 5 SaaS beta requires mandatory per-user tenant isolation and
protection of each user's data. Phase 6 adds advanced team management,
workspaces, and broader collaboration; it does not defer individual-user
isolation. Usage limits and metering are distinct from payment and billing.
Paid plans, Stripe subscriptions, payment collection, and credit packs belong
to Phase 6 under the canonical roadmap, not the Phase 5 beta MVP.

Complex source-routing decisions use the OpenAI Decisions API in the approved
target architecture. Simple queries may use deterministic routing. Filter the
trusted source catalog by authorization before routing and independently
enforce authorization before source access. Source access does not authorize
transferring query text to Decisions: the trusted server must separately
authorize that provider transfer. If transfer authorization is absent or
unclear, do not send the query. Send only the minimum query and source metadata;
never send source documents. Router and Decisions may select only from the
authorized catalog; they cannot add sources, grant permissions, bypass tenant
boundaries, or authorize provider transfers. If Decisions is unavailable, times
out, or returns invalid output, deterministic fallback may select only sources
whose eligibility and authorization can be established safely. If no safe
eligible source set can be established, stop the request. This routing fallback
is separate from JEV's whole-request lexical scoring fallback.

Source routing and its Decisions API client are planned work, not current
repository functionality. The caller's model remains responsible for final
answer generation.

## MVP Non-Goals

- BYOK.
- Multi-agent orchestration.
- SSO or advanced RBAC.
- Enterprise SLA.
- Notion connector.
- Public general-purpose REST API.

## Functional Requirements

### Evidence discovery

- Accept a query and identify the authenticated tenant/context.
- Retrieve candidates from connected and authorized document sources.
- Preserve candidate identity and source provenance through scoring and
  selection.
- Use JEV as the primary evidence scorer/ranker behind the existing
  provider-selection policy and its explicit enablement and permission gates.
- Use JEV only when explicitly enabled and permitted by policy. Before
  transferring query or candidate text to JEV, require separate trusted
  server-side authorization for that provider transfer; source access alone is
  insufficient. If authorization is absent or unclear, do not send the data.
  Minimize the transferred text.
- On any JEV failure—including provider errors, timeouts, missing, malformed,
  invalid, or incomplete scores, or any result that fails validation or cannot
  be used safely—recompute the entire candidate set lexically. Never combine
  JEV and lexical scores or rankings.
- Route complex source-selection queries through the planned Decisions API;
  deterministic routing may handle simple queries and is the fallback for
  missing, timed-out, unavailable, or invalid Decisions results. Fallback may
  use only safely eligible and authorized sources; it must not widen access or
  grant permissions, and must stop if no safe source set can be established.
- Filter the trusted source catalog by authorization before Decisions and
  independently enforce authorization before source access. Router and
  Decisions cannot add sources, grant or expand permissions, bypass tenant
  boundaries, or authorize provider data transfers.
- Send only the query and minimum source metadata for routing; never transmit
  complete source documents for that purpose.
- Leave final answer generation to the caller's model.
- Return selected evidence, stable identifiers, and appropriate source
  references without leaking data across tenants.

### Google Drive

- Allow an authorized user to connect Google Drive.
- Ingest and update documents and chunks with source identity and ownership.
- Respect authorization and deletion/revocation.
- Avoid sending source URLs or unrelated data to the scorer unless a future
  reviewed requirement explicitly needs them.

### Plans and usage

- Phase 5 free-tier usage-limit targets: 500 requests and 200K JEV tokens.
- Illustrative Pro pricing target: $19/month, with 3,000 requests and 2M
  JEV tokens. This is an estimate for planning, not an approved final price.
  Pricing, quota periods, token accounting, and paid-plan enforcement remain
  subject to explicit product decisions.
- Decisions routing metering, cost limits, and their relationship to JEV
  metering remain open for a future explicit decision.
- Phase 6 target: Stripe subscription billing and $5 credit packs.
- Enforce entitlements server-side, record usage once per request, and expose
  clear usage/error states.
- Product decisions still required: quota period, what counts as a request,
  Jev-token definition, overage behavior, credit expiration/refunds, and
  precedence between plan quota and credits.

### Comparison Lab

- Provide a “Run A/B” action for comparing eligible scorer configurations.
- Show the configurations and data scope used and distinguish score changes
  from evidence-selection changes.
- Do not silently select a winner, tune a threshold, or claim statistical
  significance without a predeclared analysis protocol.
- Protect customer content and prevent one tenant from seeing another
  tenant's experiments.

## Non-Functional Requirements

- Phase 5 per-user tenant isolation for documents, chunks, credentials, runs,
  and usage; each user's data must be protected. Phase 6 adds advanced shared
  workspace and team collaboration controls.
- Secrets stored only in an approved secret-management facility; never in
  source, reports, client-visible errors, or logs.
- Whole-request lexical scoring remains usable if JEV scoring fails.
- Deterministic source routing remains usable if the Decisions API is
  unavailable, times out, or returns invalid output.
- Provider failures are explicit, sanitized, and never converted into
  success-shaped relevance scores.
- Record provenance, model identity, SDK version, timestamps, and request
  usage when safe and available.
- Define retention, deletion, access auditing, and incident response before
  beta handling of customer documents.
- Measure latency, availability, request failures, and cost at the request
  level, avoiding repeated per-candidate accounting.

## Success Metrics

Targets, not current results:

- Free-to-paid conversion: 3–5%.
- LLM token reduction: 40–60%.
- Gross margin: 70%+ within 6–12 months.

The product team must define cohort, denominator, attribution, pricing cost
model, and measurement window for each metric before launch reporting.

## Current Product Readiness

The repository has schemas, local corpus retrieval, JEV and lexical scoring
under the provider-selection policy, an evaluation harness, and a historical
held-out single-run evaluation whose predeclared outcome was Inconclusive. It
currently implements a local stdio MCP server (`retrieve_evidence`) whose
standard path is lexical-only. Remote scoring requires a trusted, appropriately
scoped authorization boundary. It does not yet implement the hosted HTTP
service, hosted authentication or tenant-isolation enforcement, production
database or RLS, hosted provider-transfer authorization, production connectors,
dashboard, billing, or Google Drive connector. The source router and Decisions
API client are planned work, not implemented; hosted deployment is not active,
and the local health-only service is not a customer-data service. Final answer
generation remains with the caller's model. No production readiness, savings,
or generalization claim is established.

## Open Product Decisions

- Meilisearch or Postgres full-text search for lexical retrieval?
- Which pre-specified query classes require a Decisions API call, and which
  source metadata is minimally sufficient for those decisions?
- Exact definitions and periods for request/Jev-token quotas and credit packs?
- Which A/B configurations may users compare, and how is comparison consent
  and customer-data retention handled?
