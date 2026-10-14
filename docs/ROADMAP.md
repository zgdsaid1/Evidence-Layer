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

Evidence-Layer has separate routing, evidence-scoring, and answer-generation
responsibilities:

```text
User query
→ Trusted authorization-filtered source catalog
→ OpenAI Decisions API (complex source routing; planned)
→ Authorized source retrieval
→ JEV evidence scoring (only when policy allows and transfer is authorized)
→ Lexical whole-request scoring fallback on JEV failure
→ Caller’s model generates the final answer
```

- **OpenAI Decisions API** analyzes complex queries and selects a routing
  strategy and candidate sources from a trusted, authorization-filtered catalog.
  It does not score/rank evidence or generate answers. Simple queries may be
  routed deterministically without a Decisions call.
- **JEV** is the intended primary evidence-scoring and ranking provider only
  when explicitly enabled and permitted by policy.
- **Lexical** is the deterministic whole-request fallback when JEV scoring
  fails; partial provider scores are never mixed.
- **The caller's model** generates the final answer.
- **Evidence-Layer** returns selected/ranked evidence, provenance, and relevant
  metadata for the caller's model.

The source router and Decisions API client are planned, not implemented. Build
the authorized source catalog before routing and re-enforce authorization before
source access. Permission to access a source does not authorize transferring
query text to Decisions. The trusted server must have valid, explicit
authorization for that specific provider transfer before sending the query. If
authorization is absent, unclear, or invalid, do not call Decisions. Deterministic
routing may proceed without a Decisions call only when both the route and
eligible source set can be established safely and independently authorized.
If they cannot, stop rather than guessing, broadening access, or bypassing
authorization. Minimize the query and source metadata sent for routing; never
send complete source documents. Router and Decisions output cannot add sources,
grant permissions, bypass tenant boundaries, or authorize external transfers.
Decisions unavailability, timeout, or invalid output uses the same safe
deterministic fallback. This routing fallback is separate from evidence-scoring
fallback.

## 4. Strategic principle: SaaS is the long-term goal and is built incrementally

SaaS is the long-term product goal and is built incrementally. Each phase ships
a concrete, testable artifact that validates a hypothesis before the next
phase expands scope. Scope is not added ahead of validation.

## 5. North-star metric

Successful grounded tasks per week — the number of real agent tasks completed
with a correct, fully-cited, budget-compliant answer (or a correct refusal),
relative to cost and latency.

## 6. Phase 0 — Reliable MCP foundation

The implemented standard local MCP path is deterministic and uses lexical
scoring because it constructs `LocalCorpusRetriever()` without injecting a JEV
policy. Other local-retriever configurations may inject a remote JEV provider
only behind a trusted, appropriately scoped authorization boundary. The
foundation exposes the existing evidence core as a single read-only tool over
stdio, with strict validation, safe errors, deterministic ranking, tool
annotations, and logs on stderr only.

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

Phase 3 defines the EvidenceConnector interface and normalized evidence schema,
concurrent connector execution, deduplication, fusion, reranking, context-budget
allocation, connector timeouts and fallbacks, and connector health status and
reporting. Source routing selects a strategy and eligible source candidates; it
is separate from JEV evidence scoring and whole-candidate-set lexical fallback,
and the caller's final answer generation. Connector health reporting describes
connector operation and does not imply that a service health endpoint exists.

## 10. Phase 4 — Google Drive connector

Google Drive is the first production source connector. Connector priority is:

1. Google Drive (first production connector).
2. GitHub repositories.
3. Confluence or Notion.
4. SharePoint.
5. Slack or Microsoft Teams.
6. Relational databases and structured-data sources.

Local files and uploaded documents are the local base and are not a production
source connector.

## 11. Phase 5 — SaaS beta

Phase 5 delivers an individual SaaS beta with authentication and mandatory
per-user tenant isolation that protects each user's data, a personal workspace,
local-file upload, Google Drive connection, a hosted MCP HTTP endpoint, API
keys, usage metering, monitoring, and free-tier usage limits. Usage metering and
safety limits do not imply payment collection. Billing is deferred to Phase 6,
after beta reliability and usage economics are validated.

## 12. Phase 6 — Billing and expansion

Phase 6 adds Stripe subscription billing, payments, and credit packs, plus
advanced team management, multi-user workspaces, and broader collaboration and
enterprise capabilities. These build on, and do not defer, Phase 5 per-user
tenant isolation. Phase 6 capabilities include SSO, SCIM, advanced RBAC and
permission inheritance for shared workspaces, incremental sync, deletion
propagation, audit logs, data residency, admin and evaluation dashboards, and
enterprise support.

## 13. AI provider strategy

The approved architecture separates routing intelligence, evidence scoring,
deterministic fallback, and final answer generation:

```text
User query
→ Trusted authorization-filtered source catalog
→ OpenAI Decisions API (complex source routing only; planned)
→ Authorized source retrieval
→ JEV (primary scorer only when policy and transfer authorization permit)
→ Lexical (whole-request fallback only if JEV scoring fails)
→ Caller’s model (final answer generation)
```

JEV is the intended primary evidence-scoring and ranking provider only when
explicitly enabled and permitted by policy. Before transferring query or
candidate text to JEV, the trusted server must separately authorize that
provider transfer and minimize the data sent. Source access does not authorize
the transfer; if transfer authorization is absent or unclear, do not send the
data. On any JEV failure—including provider errors, timeouts, missing,
malformed, invalid, or incomplete scores, or output that fails validation—
recompute the entire candidate set lexically. Never mix JEV and lexical scores
or rankings. The final answer remains the caller model's responsibility.

OpenAI Decisions API is the required routing-intelligence component for
complex source-routing decisions; the future routing policy may use
deterministic routing for simple queries. Filter the trusted source catalog by
authorization before any Decisions call and independently re-enforce
authorization before source access. Decisions cannot add sources, grant or
expand permissions, bypass tenant boundaries, or authorize provider transfers.
Permission to access a source does not authorize transferring query text to
Decisions. The trusted server must have valid, explicit authorization for that
specific provider transfer before sending the query. If authorization is absent,
unclear, or invalid, do not call Decisions. Deterministic routing may proceed
without a Decisions call only when both the route and eligible source set can be
established safely and independently authorized. If they cannot, stop rather
than guessing, broadening access, or bypassing authorization. Minimize the query
and source metadata sent for routing; never send complete source documents.
Decisions unavailability, timeout, or invalid output uses the same safe
deterministic fallback. This is distinct from JEV's lexical scoring fallback.

The source router and Decisions API client do not yet exist. Their
authorization-filtered catalog, selective call policy, minimal input, validated
output, deterministic fallback, and fake-based tests are planned separately
from the current PR #12 JEV provider-selection scope.

### Managed keys

Provider credentials, when used, remain server-side and are not exposed to
users. Future Decisions API credentials are managed independently from JEV
scoring credentials.

Free and Pro users do not add or manage provider API keys.

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

| Plan | JEV scoring | Decisions routing | User API keys | Target user |
|---|---|---|---|---|
| Free | Platform-managed | Platform-managed | No | Individual evaluation and light use |
| Pro | Platform-managed | Platform-managed | No | Regular individual and small-team use |
| Pro+ | Platform-managed or BYOK | BYOK | Yes | Advanced users needing control |
| Enterprise | BYOK or private deployment | BYOK or private deployment | Yes | Organizations with compliance needs |

Pro+ and Enterprise are part of the later launch strategy. The initial product
focus is Free and Pro, but the Phase 5 beta uses free-tier limits; paid Pro
billing begins in Phase 6.

### Provider resilience

The system must never depend on a single external provider for its core
operation.

Routing and scoring have separate failure paths:

```text
Complex routing: Decisions API → deterministic routing fallback
Evidence scoring: JEV → whole-request lexical scoring fallback
Final answer: caller's model
```

Decisions is required for complex routing in the target architecture, but the
routing policy need not call it for every query. A routing fallback does not
trigger or alter the JEV scoring policy.

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

- Before Phase 1 validation (the benchmark proves evidence-selection value):
  Google Drive, GitHub, SharePoint, Slack, multi-tenant SaaS, billing, public
  cloud deployment, enterprise compliance certification, and custom connector
  marketplace are non-goals.
- Billing and broader public-cloud expansion remain non-goals until the SaaS
  beta (Phase 5) validates reliability and usage economics; they are introduced
  in Phase 6.

## 16. Success definition

Evidence-Layer succeeds when it measurably improves grounded-answer quality —
higher task success, faithfulness, recall, precision, and citation correctness
at lower tokens-per-successful-task, latency, failure rate, and estimated cost
— against strong baselines, and when that value converts into a validated,
incremental SaaS business.
