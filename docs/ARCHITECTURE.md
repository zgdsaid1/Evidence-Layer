# Evidence Layer Architecture

## Status

This document describes the **approved target architecture**, not deployed
infrastructure. The repository currently contains a Python library, local
evaluation scripts, dataset artifacts, a JEV scorer, and a local stdio MCP
server (`retrieve_evidence`). It does not contain a source router, Decisions
API client, or the SaaS infrastructure described below.

The repository also contains a local, health-only FastAPI service at
`services/evidence-service/`. It exposes only `GET /healthz`; it does not read
corpus content, retrieve evidence, authenticate customers, or call providers.
This local skeleton is separate from the stdio MCP server and is not a hosted
deployment or customer-data service.

Delivery phasing follows the canonical [Product Roadmap](ROADMAP.md): Phase 5
requires mandatory per-user tenant isolation that protects each user's data;
Phase 6 adds advanced team management, workspaces, billing, and broader
collaboration. Phase 6 does not defer Phase 5 isolation.

## Target System Context

```text
Agent / MCP client
       |
       v
Railway: persistent MCP server
  retrieve_evidence tool
       |
       +---- Supabase: Auth, Postgres, pgvector, Edge Functions
       |       documents, chunks, tenant data, usage
       |
        +---- Source routing (planned)
        |       deterministic routing; Decisions API for complex queries
        |       authorization-filtered source catalog
        |
        +---- Retrieval and evidence scoring
        |       JEV only when policy and transfer authorization permit
        |       whole-request lexical fallback on any JEV failure
        |       caller's model generates final answers
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
- `JevEvidenceScorer` behind the provider-selection policy; JEV is primary in
  the approved architecture, with whole-request lexical fallback.
- Current `DocumentationRAGAdapter` is a no-op/greedy baseline; it is not a
  production retrieval service.

### MCP server

- A local stdio MCP server is implemented and exposes `retrieve_evidence`.
- Its standard tool path constructs `LocalCorpusRetriever()` without an
  injected JEV policy and is lexical-only, but the retriever's default source
  boundary denies corpus reads before opening content. The tool therefore does
  not currently return corpus evidence without a future trusted source boundary.
- A separate local FastAPI health-only service exposes `GET /healthz`; it has no
  retrieval, authentication, MCP, or provider integration.
- The persistent Railway HTTP service is planned; it will host the same MCP
  protocol and `retrieve_evidence` tool.
- The future customer-facing service must authenticate/authorize the caller
  and establish tenant context.
- It must validate requests, invoke retrieval and scoring, enforce usage limits,
  and return sanitized results.
- It must keep secrets server-side and emit request-level operational metadata.

### Supabase backend (planned)

- **Postgres:** authoritative relational metadata, ownership, and usage
  records.
- **pgvector:** optional embedding/vector search if justified by retrieval
  needs; lexical scoring remains the deterministic whole-request scoring
  fallback when JEV scoring fails.
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

### JEV / TypeSafe evidence scoring

- JEV is the intended primary evidence-scoring and ranking provider only when
  explicitly enabled and permitted by policy. Before sending query or candidate
  text to JEV, the trusted server must separately authorize that provider
  transfer and minimize the data sent. Source access alone does not authorize
  this transfer; if authorization is absent or unclear, do not send the data.
- Any JEV failure—including provider errors, timeouts, missing, malformed,
  invalid, or incomplete scores, or any result that fails validation or cannot
  be used safely—requires recomputing the entire candidate set lexically. Never
  mix JEV and lexical scores or rankings.
- The target architecture calls TypeSafe only from a server-side boundary when
  JEV is enabled and permitted by plan and request policy, and separate transfer
  authorization is present. In the current implementation, live JEV transfer
  is hard-denied on supported package paths, including injected dependencies.
- Requested model defaults to `jev-latest`; record the provider-returned model
  when available because the alias may resolve to a changing concrete model.

### Source-routing intelligence (planned; not implemented)

- For complex queries, the required OpenAI Decisions API analyzes the query and
  selects a routing strategy and candidate sources from a trusted catalog that
  has already been filtered by authorization.
- Deterministic routing may handle queries classified as simple without a
  Decisions call. Decisions is required for complex routing, not for every
  query.
- Before transferring query text to Decisions, require separate trusted
  server-side authorization for that provider transfer; permission to access a
  source alone is insufficient. The trusted server must have valid, explicit
  authorization for that specific transfer before sending the query. If
  authorization is absent, unclear, or invalid, do not call Decisions. Minimize
  the query and source metadata sent; never send complete source documents.
  Independently re-enforce source authorization before access.
- Router and Decisions may select only from the server-built authorized source
  catalog. They cannot add sources, grant permissions, bypass tenant
  boundaries, or authorize provider transfers.
- If Decisions is unavailable, times out, or returns invalid output,
  deterministic fallback may proceed only when both the route and eligible
  source set can be established safely and independently authorized. The same
  rule applies when Decisions cannot be called because transfer authorization
  is absent, unclear, or invalid. Otherwise stop rather than guessing,
  broadening access, or bypassing authorization. This routing fallback is
  separate from the JEV-to-lexical evidence-scoring fallback.
- Implementing the source catalog, authorization-filtered router, selective
  Decisions client, output validation, deterministic fallback, and tests is
  future scope. No router or Decisions client currently exists.

### Final answer generation

- The caller's model generates the final answer from the authorized, selected,
  budgeted evidence. This repository does not provide an answer-generation
  provider.

### Stripe billing (planned for Phase 6)

- Manage subscriptions and $5 credit packs through verified server-side
  webhook/event processing.
- Enforce entitlements in the backend, not the frontend.
- Specify idempotency, refunds, charge disputes, credits, plan periods, and
  usage reconciliation before implementation.

## Request and Data Flow (Target)

1. MCP client calls `retrieve_evidence` with a task and candidate/source context.
2. The future MCP service authenticates the caller and derives tenant
   authorization.
3. A future router filters the trusted source catalog by authorization before
   routing. Permission to access a source does not authorize transferring query
   text to Decisions. It uses Decisions for complex queries only when the trusted
   server has valid, explicit authorization for that specific transfer; if
   authorization is absent, unclear, or invalid, it does not call Decisions.
   It sends only minimum query and source metadata. Deterministic routing may
   proceed without a Decisions call only when both the route and eligible source
   set can be established safely and independently authorized. Otherwise the
   request stops rather than guessing, broadening access, or bypassing
   authorization.
4. Retrieval queries only independently authorized sources selected by the
   routing strategy.
5. Use JEV only when explicitly enabled and permitted by policy and its query
   and candidate-text transfer is separately authorized server-side. If JEV
   fails or returns invalid or incomplete output, recompute every candidate
   score lexically; never mix provider scores. This scoring fallback is
   separate from routing fallback.
6. The service applies the configured evidence/budget policy and returns
   selected/ranked evidence with stable IDs, provenance, and relevant metadata.
7. The caller's model generates the final answer. Usage and latency are
   recorded once per request, with safe provider metadata where available.
8. The dashboard reads authorized account, source, usage, and experiment data.

This flow is a design target; production retrieval, policy, auth, storage, and
usage enforcement are not present yet.

Hosted authentication and tenant-isolation enforcement, hosted provider-transfer
authorization, production source connectors and Decisions integration, hosted
deployment, hosted database/RLS, dashboard, and billing are not implemented.
The local health-only FastAPI skeleton is implemented, but it is not a hosted
service and has no customer-data capabilities.

## Initial Data Concepts

- **Document:** tenant-owned source item with external identity, metadata,
  synchronization state, and deletion lifecycle.
- **Chunk:** document segment with stable ID, text, provenance, and optional
  embedding/vector representation.
- **Usage event:** request-level record of request count, JEV token counts,
  model identity, latency, and safe outcome category.
- **Experiment/run:** Comparison Lab configuration and aggregate result with
  explicit scope and provenance.

No production database schema or migration currently exists, and database-level
tenant controls such as PostgreSQL RLS are not implemented. Do not infer a final
schema or isolation mechanism from these logical concepts.

## Plans and Limits (Target)

- Phase 5 free-tier usage limits: 500 requests and 200K JEV tokens.
- Illustrative Phase 6 paid Pro target: $19/month, 3,000 requests and 2M JEV
  tokens, with $5 credit packs. The $19/month figure is a planning estimate,
  not an approved final price.

Quota period, request counting semantics, token metering, overage behavior, and
credit interaction are open decisions. Usage limits and metering are distinct
from payment collection. Resolve the open accounting rules before Phase 6
billing enforcement.

## Security and Reliability Principles

- Tenant authorization must be enforced on every server-side data access.
- Source-access permission does not authorize external transfer of query or
  candidate text. Require separate trusted server-side authorization for each
  Decisions or JEV transfer, minimize input, and fail closed when authorization
  is absent or unclear.
- Keep TypeSafe, Supabase service-role, Google OAuth, and Stripe secrets
  server-side; do not place them in logs or reports.
- Minimize data sent to TypeSafe and exclude source URLs and unrelated content.
- For future Decisions calls, require separate server-side transfer
  authorization; send only the query and minimum source metadata, never complete
  source documents. Filter the trusted catalog by authorization before routing
  and independently re-enforce permissions before source access.
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
- TypeSafe: external JEV evidence-scoring API.
- OpenAI Decisions API: planned source-routing intelligence for complex
  queries; not a scorer or answer generator.

These are approved target placements; none imply a current deployment.

## Open Architecture Decisions

- Meilisearch versus Postgres full-text search for lexical retrieval.
- Whether pgvector is needed in the first retrieval release and how it
  interacts with evidence scoring and ranking.
- Selective Decisions API routing criteria, source metadata schema, and
  deterministic routing fallback behavior.
- Decisions API routing quota, cost controls, and operational limits.
- Exact Supabase schema, migrations, tenant model, and retention/deletion
  policies.
- Google Drive OAuth scopes and synchronization model.
- Whether the Comparison Lab compares lexical against JEV, or other frozen
  configurations, and what user data it stores.

## Platform Deployment Target

This is the target architecture. It is **not implemented yet**: no external
project exists and nothing is deployed.

```text
Vercel:
- Next.js frontend at apps/web
- production from main
- preview deployments from PRs later

Supabase:
- Postgres + pgvector
- Auth + Storage later
- migrations are source of truth

Railway:
- future MCP/HTTP Python service
- production from main later
- no deployment until service has health endpoint and auth model
```

Repository scaffolding for these targets lives in `apps/web`, `supabase/`, and
`services/evidence-service/`. See
[ENVIRONMENT_AND_SECRETS.md](ENVIRONMENT_AND_SECRETS.md) for variable handling.
