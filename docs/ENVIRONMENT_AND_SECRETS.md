# Environment and Secrets Policy

## Rules

- The GitHub repository is public. No secrets in code, docs, issues, PRs,
  commit messages, or logs.
- `.env` files are never committed. Only `.env.example` files with variable
  names and no values are allowed.
- `.env` and `.env.*` are ignored by Git. `!.env.example` is the intentional
  exception: `.env.example` templates may be committed, with names only.
- Never paste secrets into an AI agent or chat, and do not ask an agent to
  read, print, or store them.
- Never log secrets, tokens, headers carrying credentials, or request/response
  bodies that might contain them.
- If a secret leaks, revoke and rotate it immediately, then review where it was
  exposed.
- Development, staging, and production use separate variables and separate
  credentials.

## Where variables live

| Platform | Allowed variables | Examples |
|---|---|---|
| Vercel (frontend) | Public only | `NEXT_PUBLIC_SUPABASE_URL`, `NEXT_PUBLIC_SUPABASE_ANON_KEY` (later) |
| Railway (health-only service; persistent MCP later) | `PORT` is non-secret; future server-only credentials | `SUPABASE_SERVICE_ROLE_KEY`, `JEV_API_KEY` (planned) |
| GitHub Codespaces | Encrypted Codespaces secrets | provider keys used for local work |

The Supabase service role key must never reach the frontend, a `NEXT_PUBLIC_*`
variable, or client-side code.

## Status

The synthetic-only Evidence Explorer prototype is deployed from `main` on
Vercel. The health-only Python service is deployed on Railway and reads the
non-secret `PORT` setting (default `8000`). Neither provides customer-data
operations or uses hosted database or provider credentials. The hosted backend
and its production identity/authorization boundary remain unimplemented.
