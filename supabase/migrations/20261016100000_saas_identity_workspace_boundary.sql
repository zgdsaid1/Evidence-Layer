-- Supabase Auth-backed workspace identity and default-deny membership boundary.
-- User-facing reads use the caller's verified access token through the Data API;
-- no service-role credential is used by the FastAPI request path.

create table public.workspaces (
    id uuid primary key default gen_random_uuid(),
    name text not null check (
        char_length(btrim(name)) between 1 and 120
    ),
    created_at timestamptz not null default now()
);

create table public.workspace_memberships (
    workspace_id uuid not null references public.workspaces (id) on delete cascade,
    user_id uuid not null references auth.users (id) on delete cascade,
    role text not null check (role in ('owner', 'member')),
    status text not null check (status in ('active', 'inactive')),
    created_at timestamptz not null default now(),
    constraint workspace_memberships_workspace_user_key unique (workspace_id, user_id)
);

create index workspace_memberships_user_status_workspace_idx
    on public.workspace_memberships (user_id, status, workspace_id);

alter table public.workspaces enable row level security;
alter table public.workspaces force row level security;
alter table public.workspace_memberships enable row level security;
alter table public.workspace_memberships force row level security;

-- Existing Supabase projects may grant broad default table privileges. Start
-- with no client grants, then grant only the operations exposed by this unit.
revoke all on table public.workspaces from public, anon, authenticated;
revoke all on table public.workspace_memberships from public, anon, authenticated;
grant all on table public.workspaces, public.workspace_memberships to service_role;

grant usage on schema public to authenticated;
grant select on table public.workspaces, public.workspace_memberships to authenticated;
grant update (name) on table public.workspaces to authenticated;

create policy workspaces_select_active_members
    on public.workspaces
    for select
    to authenticated
    using (
        exists (
            select 1
            from public.workspace_memberships as membership
            where membership.workspace_id = workspaces.id
              and membership.user_id = (select auth.uid())
              and membership.status = 'active'
        )
    );

create policy workspaces_update_active_owners
    on public.workspaces
    for update
    to authenticated
    using (
        exists (
            select 1
            from public.workspace_memberships as membership
            where membership.workspace_id = workspaces.id
              and membership.user_id = (select auth.uid())
              and membership.role = 'owner'
              and membership.status = 'active'
        )
    )
    with check (
        exists (
            select 1
            from public.workspace_memberships as membership
            where membership.workspace_id = workspaces.id
              and membership.user_id = (select auth.uid())
              and membership.role = 'owner'
              and membership.status = 'active'
        )
    );

-- No workspace creation/deletion or membership provisioning workflow exists
-- in this unit. Restrictive policies keep those writes closed even if a later
-- migration adds a permissive policy accidentally.
create policy workspaces_client_insert_denied
    on public.workspaces
    as restrictive
    for insert
    to authenticated
    with check (false);

create policy workspaces_client_delete_denied
    on public.workspaces
    as restrictive
    for delete
    to authenticated
    using (false);

create policy workspace_memberships_select_own_active
    on public.workspace_memberships
    for select
    to authenticated
    using (
        user_id = (select auth.uid())
        and status = 'active'
    );

create policy workspace_memberships_client_insert_denied
    on public.workspace_memberships
    as restrictive
    for insert
    to authenticated
    with check (false);

create policy workspace_memberships_client_update_denied
    on public.workspace_memberships
    as restrictive
    for update
    to authenticated
    using (false)
    with check (false);

create policy workspace_memberships_client_delete_denied
    on public.workspace_memberships
    as restrictive
    for delete
    to authenticated
    using (false);

comment on table public.workspaces is
    'SaaS workspace metadata. User access is limited by active workspace membership RLS.';
comment on table public.workspace_memberships is
    'Server-provisioned workspace roles. Clients can read only their own active memberships; client writes are denied.';
