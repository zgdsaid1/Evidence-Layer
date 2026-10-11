# Evidence-Layer Product Roadmap

## 1. Product vision

Evidence-Layer is a provider-agnostic evidence layer that sits between an AI
agent and the sources it reasons over. It turns multi-source retrieval into a
small, trustworthy, budget-governed set of cited evidence, so an agent answers
from the right evidence — or refuses safely — rather than from whatever
happened to be retrieved.

## 2. Product promise

Every answer gets the right evidence. Evidence-Layer provides evidence
retrieval, scoring, selection, provenance, permissions, and context-budget
governance so agents answer from the smallest reliable evidence set, with
citations and safe refusal.

Platform-managed provider keys must never be exposed to users, clients,
MCP responses, logs, or browser storage.

User-provided keys are a later Pro+ and Enterprise capability, with strict
encryption, isolation, rotation, and audit requirements.

## 3. Intelligence architecture

Evidence-Layer is built on three complementary intelligence layers:

```text
User query
→ Evidence-Layer
→ JEV evidence core
→ OpenAI reasoning / decision layer
→ Grounded answer and citations
```

- **Evidence-Layer** handles evidence retrieval, scoring, selection, provenance, permissions, and context-budget governance.
- **JEV evidence core** provides relevance scoring over candidate evidence.
- **OpenAI reasoning / decision layer** optionally reasons over the selected, budgeted evidence to produce a grounded answer with citations.

## 4. Strategic principle: SaaS is the long-term goal and is built incrementally

SaaS is the long-term product goal and is built incrementally. Each phase ships
a concrete, testable artifact that validates a hypothesis before the next
phase expands scope. Scope is not added ahead of validation.

## 5. North-star metric

Successful grounded tasks per week — the number of real agent tasks completed
with a correct, fully-cited, budget-compliant answer (or a correct refusal),
relative to cost and latency.

## 6. Phase 0 — Reliable MCP foundation

A deterministic, fully-local MCP server that exposes the existing evidence core
as a single read-only tool over stdio, with strict validation, safe errors,
deterministic ranking, tool annotations, and logs on stderr only. This phase
ships the MCP stdio server that has already been built and validated.

## 7. Phase 1 — Prove evidence-selection value

Phase 1 requires a benchmark comparing Evidence-Layer against strong baselines
on 20–50 real tasks. The benchmark must measure task success, answer
faithfulness, evidence recall, evidence precision, citation correctness, tokens
per successful task, latency, failure rate, correct-refusal rate, and estimated
cost.

## 8. Phase 2 — Comparison experience

Phase 2 adds scripts/compare.py and side-by-side comparison with human votes:
A, B, Tie, Both bad.

## 9. Phase 3 — Multi-source evidence architecture

Phase 3 defines an EvidenceConnector interface, normalized evidence schema,
source routing, concurrent connector execution, deduplication, fusion,
reranking, context-budget allocation, timeouts, fallbacks, and health status.

## 10. Phase 4 — Initial connectors

Connector priority is:

1. Local files and uploaded documents.
2. GitHub repositories.
3. Google Drive.
4. Confluence or Notion.
5. SharePoint.
6. Slack or Microsoft Teams.
7. Relational databases and structured-data sources.

## 11. Phase 5 — First SaaS release

Phase 5 delivers an individual SaaS release with authentication, personal
workspace, local-file upload, GitHub connection, MCP HTTP endpoint, API keys,
usage metering, monitoring, and simple billing or free-tier usage limits.

## 12. Phase 6 — Team and enterprise SaaS

Phase 6 delivers team and enterprise SaaS with multi-tenant workspaces, SSO,
SCIM, RBAC, permission inheritance, query-time authorization, incremental sync,
deletion propagation, audit logs, data residency, billing, admin dashboard,
evaluation dashboard, and enterprise support.

## 13. AI provider strategy

Evidence-Layer uses a multi-provider intelligence architecture:

```text
User query
→ Evidence-Layer
→ JEV evidence core
→ OpenAI reasoning / decision layer
→ Grounded answer and citations
```

JEV is the preferred evidence-scoring and relevance foundation.

OpenAI provides advanced reasoning, answer generation, and optional
decision-routing capabilities.

The local lexical scorer is the guaranteed offline fallback. It keeps
Evidence-Layer operational when external providers are unavailable,
unconfigured, or fail.

### Managed keys

For the initial Free and Pro plans, Evidence-Layer manages JEV and OpenAI
access on behalf of users.

Users do not add or manage provider API keys.

The platform is responsible for:

- Provider authentication.
- Key storage and rotation.
- Usage metering.
- Rate limits.
- Cost controls.
- Abuse prevention.
- Provider failover.
- Privacy and retention policies.

### Plan tiers

| Plan | JEV | OpenAI | User API keys | Target user |
|---|---|---|---|---|
| Free | Platform-managed | Platform-managed | No | Individual evaluation and light use |
| Pro | Platform-managed | Platform-managed | No | Regular individual and small-team use |
| Pro+ | Platform-managed or BYOK | BYOK | Yes | Advanced users needing control |
| Enterprise | BYOK or private deployment | BYOK or private deployment | Yes | Organizations with compliance needs |

Pro+ and Enterprise are part of the later launch strategy. The initial
development focus is Free and Pro.

### Provider resilience

The system must never depend on a single external provider for its core
operation.

```text
JEV preferred
→ OpenAI reasoning when available
→ Local lexical fallback
```

Provider failures must degrade safely to the local lexical core.

The active provider path must be recorded in non-sensitive metadata.

Provider errors, API keys, and internal exception details must never be
exposed in MCP responses or stdout.

Platform-managed provider keys must never be exposed to users, clients,
MCP responses, logs, or browser storage.

User-provided keys are a later Pro+ and Enterprise capability, with strict
encryption, isolation, rotation, and audit requirements.

## 14. Differentiating capabilities

- Evidence Authority Layer.
- Conflict-aware answers.
- Freshness governance.
- Permission-aware retrieval.
- Budget-aware evidence selection.
- Human-in-the-loop evaluation.
- Answer auditability.

## 15. Non-goals before validation

Google Drive, SharePoint, Slack, multi-tenant SaaS, billing, public cloud
deployment, enterprise compliance certification, and custom connector
marketplace are non-goals before Phase 1 and Phase 5 validation.

## 16. Success definition

Evidence-Layer succeeds when it measurably improves grounded-answer quality —
higher task success, faithfulness, recall, precision, and citation correctness
at lower tokens-per-successful-task, latency, failure rate, and estimated cost
— against strong baselines, and when that value converts into a validated,
incremental SaaS business.
