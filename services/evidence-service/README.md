# Evidence Layer service

This local FastAPI service exposes a public `GET /healthz`, plus a small
Supabase Auth identity and workspace-membership boundary:

- `GET /v1/me` returns the verified Supabase user ID, verified issuer, and the
  caller's active workspace memberships and roles.
- `GET /v1/workspaces/{workspace_id}` selects one workspace only after the
  caller's active membership has been checked.

The service does not expose evidence retrieval, source connectors, JEV,
Decisions, answer generation, or a login/signup flow. `/healthz` does not
depend on Supabase configuration or credentials. Protected routes return an
error when the required identity configuration is absent or invalid.

## Identity and tenant boundary

Protected requests require a Supabase Auth access token in the
`Authorization: Bearer <token>` header. The service verifies its signature
using the configured project's Supabase JWKS, then checks the exact issuer, the `authenticated`
audience and role, the token type header, user subject UUID, expiry and other
time claims, and that the token is not an anonymous Auth user. Verification
uses a 30-second clock leeway. JWKS are cached for at most 300 seconds; an
unknown `kid` triggers a refresh, rate-limited to one unknown-key refresh per
second. A failed refresh or unknown key fails closed.

Only asymmetric Supabase signing algorithms `ES256` and `RS256` are accepted.
Supabase's legacy `HS256` signing secret is not accepted or stored by this
service. Before connecting a project, configure its Auth signing keys to use an
asymmetric key and set the exact active algorithm in
`SUPABASE_JWT_ALGORITHMS`. The repository does not identify a linked Supabase
project or establish its current signing-key configuration.

The access token is forwarded to Supabase's Data API with the publishable API
key, so Postgres evaluates RLS as that user. The service never uses a
`service_role` or secret API key on a user request. It uses verified `(issuer,
subject)` identity; email and client-supplied IDs are not identity evidence.
The current configuration is for one Supabase Auth issuer. Supporting another
issuer requires a trusted issuer/subject-to-internal-user mapping; identities
must not be linked by email.

`workspaces` are visible only through an active membership. Owners may update
the workspace name; members may read. Users may read only their own active
membership rows. Client workspace creation/deletion and membership
insert/update/delete are denied to user-facing roles. The Supabase
`service_role` remains a privileged administrative role that bypasses RLS and
is not used by this service's request path. No workspace bootstrap,
invitation, membership assignment, or role-change endpoint is included.
Provisioning memberships therefore remains a trusted administrative operation
until a separate server-side flow is reviewed. An owner cannot use this API to
manage or escalate memberships.

## Local configuration

Use `.env.example` as a template and export the variables through your local
shell or runtime environment; this service does not load `.env` files itself.
Do not commit populated values. Required variables are:

| Variable | Meaning |
| --- | --- |
| `SUPABASE_URL` | Project API base URL, without a path; its origin must match the configured Auth issuer |
| `SUPABASE_PUBLISHABLE_KEY` | `sb_publishable_...` key used to reach the Data API; secret/service-role and legacy JWT API keys are rejected |
| `SUPABASE_JWT_ISSUER` | Exact Auth issuer, usually `https://<project-ref>.supabase.co/auth/v1` |
| `SUPABASE_JWT_AUDIENCE` | Must be `authenticated` |
| `SUPABASE_JWT_ALGORITHMS` | Exact supported asymmetric algorithms enabled for Auth, `ES256` and/or `RS256` |
| `SUPABASE_JWKS_CACHE_TTL_SECONDS` | Optional key cache duration from 1 to 300 seconds; defaults to 300 |

The JWKS endpoint is derived from the issuer as
`<issuer>/.well-known/jwks.json`. No real project values are checked into this
repository. If settings are unset, incomplete, use HTTP outside loopback, or
request an unsupported algorithm, protected routes fail closed while health
continues to work.

## Local use and tests

Use Python 3.12 or newer, from the repository root:

```bash
python -m pip install -e ".[dev,service]"
PYTHONPATH=services/evidence-service python -m evidence_service
```

The entry point binds to `0.0.0.0` and reads `PORT`, defaulting to `8000`.
The equivalent Uvicorn command is:

```bash
PYTHONPATH=services/evidence-service python -m uvicorn evidence_service.app:app \
  --host 0.0.0.0 --port "${PORT:-8000}" --no-access-log
```

Run unit and service tests from the repository root:

```bash
PYTHONDONTWRITEBYTECODE=1 python -m pytest -p no:cacheprovider tests/test_evidence_service_health.py tests/test_evidence_service_auth.py
PYTHONDONTWRITEBYTECODE=1 python -m pytest -p no:cacheprovider tests/test_evidence_service_config.py tests/test_evidence_service_repository.py
PYTHONDONTWRITEBYTECODE=1 python -m pytest -p no:cacheprovider
```

The RLS integration tests execute PostgreSQL policies under Supabase's
`authenticated` and `anon` roles with request claim context. They need the
Supabase local stack and Docker; they do not use or link a remote project:

```bash
supabase start
supabase db reset --local
supabase test db --local
supabase stop --no-backup
```

The SQL test creates synthetic users/workspaces inside a rollback-only test
transaction, temporarily grants extra DML only within that transaction to
prove the RLS write-deny policies, and rolls back all fixture data.

## Container and deployment status

Build the service image locally with the repository root as the context:

```bash
docker build -f services/evidence-service/Dockerfile -t evidence-service:local .
```

The image runs as a non-root user. The health check calls only `/healthz`.
This change does not configure Railway, link a Supabase project, apply a remote
migration, or deploy the service. Railway remains a future deployment target;
no hosted deployment is established by this repository change.
