# Supabase

Target role: Postgres + pgvector now; Auth and Storage later. Nothing here is
linked to a Supabase project yet.

## Rules

- Schema changes are made only through versioned migrations in
  `supabase/migrations/`. Migrations are the source of truth.
- Never edit a production database by hand from Studio or the SQL editor.
- Planned flow: local CLI -> migration review -> staging -> production.
- Never commit a `.env` file, project URL with keys, or any secret. See
  [docs/ENVIRONMENT_AND_SECRETS.md](../docs/ENVIRONMENT_AND_SECRETS.md).

## Current state

`migrations/20261007170000_platform_baseline.sql` only enables the `vector`
extension. Product tables, RLS policies, and storage buckets will be added in
later migrations.
