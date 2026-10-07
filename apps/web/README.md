# apps/web

Minimal Next.js (App Router, TypeScript) skeleton intended for Vercel later.
It renders a single static page. There is no auth, Supabase client, API route,
Stripe, external asset, or environment variable usage yet.

Dependencies are not installed and nothing is deployed or linked to Vercel.

## Vercel

When a Vercel project is created later, set **Root Directory** to `apps/web`.
Only public variables (`NEXT_PUBLIC_*`) may ever be configured there; see
[docs/ENVIRONMENT_AND_SECRETS.md](../../docs/ENVIRONMENT_AND_SECRETS.md).

## Local development (later)

```bash
cd apps/web
npm install
npm run dev
```
