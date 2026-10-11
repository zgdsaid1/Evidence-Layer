# ADR 0002 — Multi-source evidence architecture

- Status: Proposed

## Context

Evidence-Layer must eventually answer from many sources (local files, GitHub,
Google Drive, Confluence/Notion, SharePoint, Slack/Teams, and structured
databases). Multi-source retrieval is only trustworthy if every source is
normalized into one evidence model, fused and reranked consistently, and if
permissions, provenance, and context budget are enforced at query time.
Building connectors ad hoc, without a shared contract, would produce
inconsistent retrieval and ungoverned context.

## Decision

Adopt a multi-source evidence architecture built on a single normalized
evidence schema and a pluggable EvidenceConnector interface. Every source is
read through a connector that returns normalized evidence; the pipeline then
deduplicates, fuses, reranks, and selects within a context budget before
producing a grounded answer with citations.

## Core principles

- One normalized evidence schema for every source.
- A single EvidenceConnector interface for retrieval, routing, timeouts,
  fallbacks, and health.
- Permission-aware retrieval enforced at query time.
- Deterministic evidence selection within an explicit context budget.
- Provenance and citations preserved end to end.
- Safe refusal when evidence is insufficient or conflicting.
- The local rule-based router remains the default fallback.

## Architecture diagram

```
User query
  → Source router
  → Connectors
  → Normalized evidence
  → Deduplication and fusion
  → Reranking
  → Evidence selection within context budget
  → Grounded answer with citations
```

## Connector priorities

1. Local files and uploaded documents.
2. GitHub repositories.
3. Google Drive.
4. Confluence or Notion.
5. SharePoint.
6. Slack or Microsoft Teams.
7. Relational databases and structured-data sources.

## Intelligence and provider strategy

Evidence-Layer uses a multi-provider intelligence architecture:

```
User query
→ Evidence-Layer
→ JEV evidence core
→ OpenAI reasoning / decision layer
→ Grounded answer and citations
```

- **JEV** is the preferred evidence-scoring and relevance foundation.
- **OpenAI** is optional and provides advanced reasoning, answer generation,
  and optional decision-routing capabilities. It must never replace evidence
  selection, permission enforcement, provenance, auditability, context-budget
  governance, or safe refusal behavior.
- **Local lexical scorer** is the guaranteed offline fallback. Core operation
  must not depend on a single external provider; provider failures must degrade
  safely to the local lexical core.

For the initial Free and Pro plans, JEV and OpenAI access are platform-managed.
Users must not add or manage provider API keys.

Pro+ and Enterprise are later capabilities. They may support platform-managed
JEV or BYOK, OpenAI BYOK, or private deployment as applicable. Any user-provided
key capability must require strict encryption, tenant isolation, rotation, and
audit controls.

Platform-managed provider keys must never be exposed to users, clients, MCP
responses, logs, or browser storage.

Provider errors, API keys, and internal exception details must never be exposed
in MCP responses or stdout.

The active provider path must be recorded only in non-sensitive metadata.

## Consequences

- Positive: a single evidence contract simplifies connectors, fusion,
  reranking, and governance, and makes retrieval consistent and auditable.
- Positive: permission, provenance, and budget are enforced in one place, not
  per connector.
- Cost: every connector must implement the normalized schema and satisfy
  timeouts, fallbacks, and health reporting.
- Risk: source-specific ranking differences must be reconciled by the
  fusion/reranking stage; the rule-based router remains the safe default until
  intelligent routing is validated.
- Better reasoning when OpenAI is available.
- Continued offline and provider-independent core operation through the local
  lexical fallback.
- Operational responsibility for authentication, key rotation, usage metering,
  rate limits, cost controls, abuse prevention, failover, privacy, and
  retention when keys are platform-managed.
- More implementation and evaluation complexity because all provider paths and
  safe fallback behavior must be tested.
