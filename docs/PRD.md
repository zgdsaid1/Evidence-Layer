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

1. Provide an MCP `find_evidence` tool.
2. Retrieve and rank candidate evidence with the existing lexical scorer as
   default and fallback.
3. Offer Jev as an explicitly optional scoring layer.
4. Store documents, chunks, and usage in Supabase.
5. Connect Google Drive as the first source connector.
6. Offer the defined Free and Pro tiers, Stripe subscriptions, and credit
   packs.
7. Provide a Comparison Lab that runs and presents an A/B comparison.

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
- Rank by lexical scoring by default.
- Allow Jev only as an explicitly enabled optional scorer; fall back to lexical
  when Jev is unavailable or disabled.
- Return selected evidence, stable identifiers, and appropriate source
  references without leaking data across tenants.

### Google Drive

- Allow an authorized user to connect Google Drive.
- Ingest and update documents and chunks with source identity and ownership.
- Respect authorization and deletion/revocation.
- Avoid sending source URLs or unrelated data to the scorer unless a future
  reviewed requirement explicitly needs them.

### Plans and usage

- Free target: 500 requests and 200K Jev tokens.
- Pro target: $19/month, 3,000 requests, and 2M Jev tokens.
- Support Stripe subscription billing and $5 credit packs.
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

- Tenant isolation for documents, chunks, credentials, runs, and usage.
- Secrets stored only in an approved secret-management facility; never in
  source, reports, client-visible errors, or logs.
- Lexical path remains usable if the optional provider is unavailable.
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

The repository has schemas, local lexical ranking, an optional Jev scorer, an
evaluation harness, and a held-out single-run evaluation whose predeclared
outcome was Inconclusive. It does not currently implement the hosted product,
MCP server, database, dashboard, billing, or Google Drive connector. No
production readiness, savings, or generalization claim is established.

## Open Product Decisions

- Meilisearch or Postgres full-text search for lexical retrieval?
- Beta launch with or without billing?
- Exact definitions and periods for request/Jev-token quotas and credit packs?
- Which A/B configurations may users compare, and how is comparison consent
  and customer-data retention handled?
