# Evidence Layer Architecture

## Status

This document describes the **approved target architecture**, not deployed
infrastructure. The repository currently contains a Python library, local
evaluation scripts, dataset artifacts, and an optional TypeSafe/Jev scorer. It
does not contain the SaaS infrastructure described below.

## Target System Context

```text
Agent / MCP client
       |
       v
Railway: persistent MCP server
  find_evidence tool
       |
       +---- Supabase: Auth, Postgres, pgvector, Edge Functions
       |       documents, chunks, tenant data, usage
       |
       +---- Retrieval and scoring
       |       lexical default + lexical fallback
       |       optional Jev via TypeSafe API
       |
       +---- Vercel: Next.js dashboard
               connections, usage, Comparison Lab
```

Stripe handles plan billing and credit packs through server-side, auditable
billing workflows. It is a billing integration, not the source of truth for
document data or scorer behavior.

## Components and Responsibilities

### Python evidence core (exists)

- Provider-agnostic Pydantic schemas for tasks, candidates, policy, results,
  and evaluation cases.
- Deterministic `LexicalScorer`, candidate ranking, and evaluation metrics.
- Optional `JevEvidenceScorer` behind the same scorer interface.
- Current `DocumentationRAGAdapter` is a no-op/greedy baseline; it is not a
  production retrieval service.

### Railway MCP server (planned)

- Run as a persistent service hosting the MCP protocol.
- Expose `find_evidence` as the first tool.
- Authenticate/authorize the caller and establish tenant context.
- Validate requests, invoke retrieval and scoring, enforce usage limits, and
  return sanitized results.
- Keep secrets server-side and emit request-level operational metadata.

### Supabase backend (planned)

- **Postgres:** authoritative relational metadata, ownership, and usage
  records.
- **pgvector:** optional embedding/vector search if justified by retrieval
  needs; lexical retrieval remains a required baseline/fallback.
- **Auth:** user identity and authentication integration.
- **Edge Functions:** narrowly scoped backend operations where appropriate;
  do not duplicate core scoring semantics without a defined boundary.
- Initial logical entities: tenants/users, connected sources, documents,
  chunks, ingestion state, and usage events. Exact schema and migrations are
  not yet defined.

### Vercel dashboard (planned)

- Next.js frontend for account setup, Google Drive connection, usage and plan
  visibility, and the Comparison Lab.
- The browser must not receive provider keys, database service-role secrets,
  or unrestricted billing credentials.

### Google Drive connector (planned)

- Authenticate the user's delegated access, ingest authorized files, retain
  source identity, support synchronization and deletion, and enforce tenant
  boundaries.
- OAuth scopes, sync strategy, supported file types, retention, and error
  semantics remain to be specified.

### Jev / TypeSafe (optional)

- Call TypeSafe only from a server-side boundary when Jev is enabled and
  permitted by plan and request policy.
- Requested model defaults to `jev-latest`; record the provider-returned model
  when available because the alias may resolve to a changing concrete model.
- Keep the optional SDK out of default core imports.
- On disabled provider, dependency failure, or request failure, preserve the
  lexical path and report provider failure safely; never disguise failure as a
  valid score.

### Stripe billing (planned)

- Manage subscriptions and $5 credit packs through verified server-side
  webhook/event processing.
- Enforce entitlements in the backend, not the frontend.
- Specify idempotency, refunds, charge disputes, credits, plan periods, and
  usage reconciliation before implementation.

## Request and Data Flow (Target)

1. MCP client calls `find_evidence` with a task and candidate/source context.
2. MCP service authenticates the caller and derives tenant authorization.
3. Retrieval queries only that tenant's authorized indexed content.
4. Lexical scoring ranks candidates by default. If optional Jev is enabled and
   allowed, Jev may score or rerank candidates behind the scorer boundary.
5. Lexical remains available as the fallback when Jev is not used or fails.
6. The service applies the configured evidence/budget policy and returns
   selected evidence with stable IDs and provenance.
7. Usage and latency are recorded once per request, with safe model/provider
   metadata where available.
8. The dashboard reads authorized account, source, usage, and experiment data.

This flow is a design target; production retrieval, policy, auth, storage, and
usage enforcement are not present yet.

## Initial Data Concepts

- **Document:** tenant-owned source item with external identity, metadata,
  synchronization state, and deletion lifecycle.
- **Chunk:** document segment with stable ID, text, provenance, and optional
  embedding/vector representation.
- **Usage event:** request-level record of request count, Jev token counts,
  model identity, latency, and safe outcome category.
- **Experiment/run:** Comparison Lab configuration and aggregate result with
  explicit scope and provenance.

No database schema or migration currently exists. Do not infer a final schema
from these logical concepts.

## Plans and Limits (Target)

- Free: 500 requests and 200K Jev tokens.
- Pro: $19/month, 3,000 requests and 2M Jev tokens.
- Credit packs: $5.

Quota period, request counting semantics, token metering, overage behavior, and
credit interaction are open decisions. They must be resolved before billing
enforcement.

## Security and Reliability Principles

- Tenant authorization is enforced on every server-side data access.
- Keep TypeSafe, Supabase service-role, Google OAuth, and Stripe secrets
  server-side; do not place them in logs or reports.
- Minimize data sent to TypeSafe and exclude source URLs and unrelated content.
- Sanitize provider errors and avoid request/response body logging.
- Validate connector authorization, deletion, and revocation behavior.
- Use explicit provider errors and lexical fallback rather than returning
  success-shaped defaults.
- Track retries, idempotency, rate limits, and request-level usage explicitly
  before production launch.

## Deployment Boundaries

- Vercel: Next.js dashboard.
- Supabase: backend services and data.
- Railway: persistent MCP server only.
- TypeSafe: external optional Jev scoring API.

These are approved target placements; none imply a current deployment.

## Open Architecture Decisions

- Meilisearch versus Postgres full-text search for lexical retrieval.
- Whether pgvector is needed in the first retrieval release and how it
  interacts with lexical ranking.
- Beta launch with billing or without billing.
- Exact Supabase schema, migrations, tenant model, and retention/deletion
  policies.
- Google Drive OAuth scopes and synchronization model.
- Whether the Comparison Lab compares lexical against Jev, or other frozen
  configurations, and what user data it stores.
