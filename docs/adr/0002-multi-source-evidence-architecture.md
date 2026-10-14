# ADR 0002 — Multi-source evidence architecture

- Status: Accepted

## Context

Evidence-Layer must eventually retrieve eligible evidence from many sources
(local files, GitHub, Google Drive, Confluence/Notion, SharePoint, Slack/Teams,
and structured databases) to support the caller's answers. Multi-source
retrieval is only trustworthy if every source is normalized into one evidence
model, fused and ranked consistently, and if permissions, provenance, and
context budget are enforced at query time. Building connectors ad hoc, without
a shared contract, would produce inconsistent retrieval and ungoverned
context.

## Decision

Adopt a multi-source evidence architecture built on a single normalized
evidence schema and a pluggable EvidenceConnector interface. Every source is
read through a connector that returns normalized evidence; the pipeline then
deduplicates, fuses, scores and ranks candidates, and selects eligible evidence
within a context budget. Evidence-Layer returns the selected evidence,
provenance, and relevant metadata. The calling application or model generates
the final natural-language answer.

## Core principles

- One normalized evidence schema for every source.
- Separate source-routing, connector, and evidence-scoring responsibilities.
- Each connector must enforce source-native delegated authorization and ACL
  propagation; the future central pipeline must enforce normalized tenant
  policy, query-time authorization, and tenant data isolation.
- Deterministic evidence selection within an explicit context budget.
- Provenance and citations preserved end to end.
- Safe refusal when evidence is insufficient or conflicting.
- A server-built source catalog is filtered by authorization before routing.
  Router and Decisions output may select only strategies and source candidates
  from that catalog; neither may add sources, grant or expand permissions,
  bypass tenant isolation, or authorize provider data transfer.
- Authorization to access a source does not authorize transferring query or
  candidate text to an external provider. Each such transfer requires explicit
  trusted server-side authorization for that provider and request. If
  authorization is absent or unclear, do not transfer the data.
- Routing fallback and evidence-scoring fallback are distinct mechanisms.

## Architecture diagram

```
User query
  → Authorization-filtered trusted source catalog
  → Deterministic routing, or OpenAI Decisions API for complex queries
  → Connectors
  → Normalized evidence
  → Deduplication and fusion
  → JEV evidence scoring and ranking when explicitly enabled and authorized
      (otherwise lexical; whole-request lexical recomputation on JEV failure)
  → Evidence selection within context budget
  → Evidence-Layer returns selected evidence and provenance
  → Caller's model generates the final answer
```

The source router and Decisions API client are planned work; neither is
implemented in this repository. Decisions is the intended mechanism for complex
source-routing queries; simple queries may use deterministic routing. Decisions
may analyze the query and select a strategy and candidate sources only from the
server-built, authorization-filtered catalog. Its output cannot grant
permissions, bypass tenant boundaries, or authorize a provider transfer.

Before sending query text to Decisions, the future host must explicitly
authorize that provider transfer on the trusted server side and minimize the
input to the query and minimum source metadata needed for routing; never send
complete source documents for routing. If Decisions is unavailable, times out,
or returns invalid output, deterministic fallback may select only sources whose
eligibility and authorization can be established safely. The fallback must not
widen access. If no safe eligible source set can be established, stop the
request safely. Recheck authorization independently before any selected source
is accessed.

## Implementation status and delivery boundary

This ADR records accepted target architecture requirements; it does not claim
that their production controls or services are implemented. The repository has
a local Python evidence core and a local stdio MCP server. The standard MCP/
stdio path remains lexical-only; remote scoring is permitted only where a
trusted, appropriately scoped authorization boundary explicitly allows it. The
hosted service, hosted authentication and tenant isolation, production source
connectors, hosted provider-transfer authorization, production Decisions
integration, hosted deployment, hosted database/RLS, dashboard, and billing
are not implemented.

The canonical roadmap's Phase 5 SaaS beta requires authentication and
mandatory per-user tenant isolation that protects each user's data. Phase 6 adds
advanced team management and workspaces. Those collaboration features do not
defer the individual-user isolation required for the beta. These are delivery
requirements, not claims of current implementation.

## Connector priorities

1. Google Drive (first production connector).
2. GitHub repositories.
3. Confluence or Notion.
4. SharePoint.
5. Slack or Microsoft Teams.
6. Relational databases and structured-data sources.

Local files and uploaded documents are the local base and are not a production
source connector.

## Intelligence and provider strategy

The approved architecture separates routing intelligence, evidence scoring,
deterministic fallback, and final answer generation:

```
User query
→ OpenAI Decisions API (complex source routing only; planned)
→ Authorized source retrieval
→ JEV (primary evidence scoring and ranking)
→ Lexical (whole-request fallback only if JEV scoring fails)
→ Caller's model (final answer generation)
```

- **OpenAI Decisions API** is the required routing-intelligence component for
  complex source-routing decisions. The future router may use deterministic
  routing for queries that do not require a Decisions call. Decisions selects a
  strategy and candidate sources; it does not score evidence, rank evidence, or
  generate answers. The router and client are planned, not implemented. Before
  sending query text, the future host must explicitly authorize the Decisions
  transfer server-side and send only the minimum required query and source
  metadata; never send full source documents.
- **Authorization** filters the trusted source catalog before any Decisions
  call and is independently enforced before source access. Decisions output
  cannot add source identifiers, grant or expand permissions, bypass tenant
  boundaries, or authorize provider data transfer. On Decisions unavailability,
  timeout, or invalid output, deterministic routing may select only safely
  eligible and authorized sources; if none can be established, stop the request
  safely.
- **JEV** is the intended primary evidence-scoring and ranking provider only
  when explicitly enabled and permitted by policy. Before sending query or
  candidate text to JEV, the future host must separately authorize that provider
  transfer server-side and minimize the transferred data to what scoring needs.
  Source access authorization alone is insufficient. If transfer authorization
  is absent or unclear, do not call JEV.
- **Lexical** scoring is local. Provider errors, timeouts, missing, malformed,
  invalid, or incomplete scores, or any JEV result that fails validation or
  cannot be used safely, constitute JEV failure. Recompute scores for the entire
  candidate set lexically; never combine JEV and lexical scores or rankings.
  Separately, deterministic source routing handles simple queries and is the
  safe fallback for Decisions unavailability, timeout, or invalid output.
- **The caller's model** remains responsible for final answer generation.

In the target architecture, provider credentials remain server-side and are
not exposed to users. Any future Decisions API credentials are managed
independently from JEV scoring credentials.

Any future user-provided key capability must require strict encryption, tenant
isolation, rotation, and audit controls.

The target architecture must never expose platform-managed provider keys to
users, clients, MCP responses, logs, or browser storage.

As a target security requirement, provider errors, API keys, and internal
exception details must never be exposed in MCP responses or stdout.

For future provider-enabled requests, record the active provider path only in
non-sensitive metadata.

## Consequences

- Positive: a single evidence contract simplifies connectors, fusion,
  reranking, and governance, and makes retrieval consistent and auditable.
- Positive: the future central pipeline must enforce normalized tenant policy,
  query-time authorization, tenant isolation, provenance, and budgets, while
  each connector enforces source-native authorization and ACLs.
- Cost: every connector must implement the normalized schema and satisfy
  timeouts, fallbacks, and health reporting.
- Risk: source-specific ranking differences must be reconciled by the
  evidence-scoring and selection stages. Decisions is required for complex
  routing; simple queries may route deterministically. On Decisions
  unavailability, timeout, or invalid output, deterministic fallback must stay
  within the safely eligible, authorized source set or stop the request.
- Remote JEV scoring is used only when explicitly enabled and authorized,
  including separate server-side authorization for transferring query and
  candidate text. Any JEV failure requires full-candidate-set lexical
  recomputation; provider rankings are never mixed.
- Evidence-Layer returns selected evidence, provenance, and relevant metadata;
  the caller's model generates the final answer.
- Operational responsibility for authentication, key rotation, usage metering,
  rate limits, cost controls, abuse prevention, failover, privacy, and
  retention for provider credentials.
- More implementation and evaluation complexity because all provider paths and
  safe fallback behavior must be tested.
