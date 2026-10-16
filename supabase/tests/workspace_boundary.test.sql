begin;

create extension if not exists pgtap with schema extensions;

select plan(22);

select ok((select relrowsecurity from pg_class where oid = 'public.workspaces'::regclass), 'RLS is enabled on workspaces');
select ok((select relrowsecurity from pg_class where oid = 'public.workspace_memberships'::regclass), 'RLS is enabled on workspace memberships');

-- Synthetic users and memberships are provisioned as the database owner. User
-- requests below run as normal Supabase roles with PostgREST-style JWT claims.
insert into auth.users (id, aud, role, email)
values
    ('10000000-0000-4000-8000-000000000001', 'authenticated', 'authenticated', 'a@example.test'),
    ('20000000-0000-4000-8000-000000000002', 'authenticated', 'authenticated', 'b@example.test');

insert into public.workspaces (id, name)
values
    ('a1000000-0000-4000-8000-000000000001', 'A primary'),
    ('a2000000-0000-4000-8000-000000000002', 'A secondary'),
    ('b3000000-0000-4000-8000-000000000003', 'B only');

insert into public.workspace_memberships (workspace_id, user_id, role, status)
values
    ('a1000000-0000-4000-8000-000000000001', '10000000-0000-4000-8000-000000000001', 'owner', 'active'),
    ('a2000000-0000-4000-8000-000000000002', '10000000-0000-4000-8000-000000000001', 'member', 'active'),
    ('b3000000-0000-4000-8000-000000000003', '10000000-0000-4000-8000-000000000001', 'member', 'inactive'),
    ('a1000000-0000-4000-8000-000000000001', '20000000-0000-4000-8000-000000000002', 'member', 'active'),
    ('b3000000-0000-4000-8000-000000000003', '20000000-0000-4000-8000-000000000002', 'owner', 'active');

create temporary table workspace_rls_observations (
    name text primary key,
    value text not null
);
grant insert, select on workspace_rls_observations to authenticated, anon;

-- Temporarily over-grant DML inside this rollback-only test transaction. This
-- verifies that RLS itself denies writes; the migration grants less privilege.
grant insert, update, delete on public.workspaces to authenticated;
grant insert, update, delete on public.workspace_memberships to authenticated;

set local role authenticated;
select set_config('request.jwt.claim.sub', '10000000-0000-4000-8000-000000000001', true);
select set_config(
    'request.jwt.claims',
    '{"sub":"10000000-0000-4000-8000-000000000001","role":"authenticated","aud":"authenticated"}',
    true
);

insert into workspace_rls_observations
values
    ('a_workspaces', (select count(*)::text from public.workspaces)),
    ('a_active_memberships', (select count(*)::text from public.workspace_memberships)),
    ('a_other_users_memberships', (
        select count(*)::text from public.workspace_memberships
        where user_id = '20000000-0000-4000-8000-000000000002'
    )),
    ('a_inactive_membership', (
        select count(*)::text from public.workspace_memberships
        where workspace_id = 'b3000000-0000-4000-8000-000000000003'
    )),
    ('a_b_only_workspace', (
        select count(*)::text from public.workspaces
        where id = 'b3000000-0000-4000-8000-000000000003'
    ));

do $$
declare
    affected integer;
begin
    update public.workspaces
    set name = 'A primary renamed'
    where id = 'a1000000-0000-4000-8000-000000000001';
    get diagnostics affected = row_count;
    insert into pg_temp.workspace_rls_observations values ('a_owner_rename', affected::text);

    update public.workspaces
    set name = 'unauthorized member rename'
    where id = 'a2000000-0000-4000-8000-000000000002';
    get diagnostics affected = row_count;
    insert into pg_temp.workspace_rls_observations values ('a_member_rename', affected::text);

    update public.workspaces
    set name = 'unauthorized cross-workspace rename'
    where id = 'b3000000-0000-4000-8000-000000000003';
    get diagnostics affected = row_count;
    insert into pg_temp.workspace_rls_observations values ('a_b_workspace_rename', affected::text);

    update public.workspace_memberships
    set workspace_id = 'b3000000-0000-4000-8000-000000000003'
    where workspace_id = 'a1000000-0000-4000-8000-000000000001'
      and user_id = '10000000-0000-4000-8000-000000000001';
    get diagnostics affected = row_count;
    insert into pg_temp.workspace_rls_observations values ('a_membership_move', affected::text);

    update public.workspace_memberships
    set role = 'owner'
    where workspace_id = 'a2000000-0000-4000-8000-000000000002'
      and user_id = '10000000-0000-4000-8000-000000000001';
    get diagnostics affected = row_count;
    insert into pg_temp.workspace_rls_observations values ('a_self_promotion', affected::text);

    update public.workspace_memberships
    set role = 'owner'
    where workspace_id = 'a1000000-0000-4000-8000-000000000001'
      and user_id = '20000000-0000-4000-8000-000000000002';
    get diagnostics affected = row_count;
    insert into pg_temp.workspace_rls_observations values ('a_other_membership_update', affected::text);

    delete from public.workspace_memberships
    where workspace_id = 'a1000000-0000-4000-8000-000000000001'
      and user_id = '10000000-0000-4000-8000-000000000001';
    get diagnostics affected = row_count;
    insert into pg_temp.workspace_rls_observations values ('a_membership_delete', affected::text);

    delete from public.workspaces
    where id = 'b3000000-0000-4000-8000-000000000003';
    get diagnostics affected = row_count;
    insert into pg_temp.workspace_rls_observations values ('a_workspace_delete', affected::text);
end $$;

do $$
begin
    insert into public.workspace_memberships (workspace_id, user_id, role, status)
    values (
        'b3000000-0000-4000-8000-000000000003',
        '10000000-0000-4000-8000-000000000001',
        'owner',
        'active'
    );
    insert into pg_temp.workspace_rls_observations values ('a_membership_insert', 'not denied');
exception when insufficient_privilege then
    insert into pg_temp.workspace_rls_observations values ('a_membership_insert', '42501');
end $$;

do $$
begin
    insert into public.workspaces (name) values ('forged workspace');
    insert into pg_temp.workspace_rls_observations values ('a_workspace_insert', 'not denied');
exception when insufficient_privilege then
    insert into pg_temp.workspace_rls_observations values ('a_workspace_insert', '42501');
end $$;

reset role;

select is((select value from workspace_rls_observations where name = 'a_workspaces'), '2', 'A sees only workspaces with active memberships');
select is((select value from workspace_rls_observations where name = 'a_active_memberships'), '2', 'A sees multiple active memberships of its own');
select is((select value from workspace_rls_observations where name = 'a_other_users_memberships'), '0', 'A cannot read another user membership, even in a shared workspace');
select is((select value from workspace_rls_observations where name = 'a_inactive_membership'), '0', 'A cannot read its inactive membership');
select is((select value from workspace_rls_observations where name = 'a_b_only_workspace'), '0', 'A cannot read B-only workspace metadata');
select is((select value from workspace_rls_observations where name = 'a_owner_rename'), '1', 'An active owner can update workspace metadata');
select is((select value from workspace_rls_observations where name = 'a_member_rename'), '0', 'An active member cannot update workspace metadata');
select is((select value from workspace_rls_observations where name = 'a_b_workspace_rename'), '0', 'A cannot update B-only workspace metadata');
select is((select value from workspace_rls_observations where name = 'a_membership_move'), '0', 'A cannot move a membership between workspace IDs');
select is((select value from workspace_rls_observations where name = 'a_self_promotion'), '0', 'A cannot promote its own membership role');
select is((select value from workspace_rls_observations where name = 'a_other_membership_update'), '0', 'A cannot modify another user membership');
select is((select value from workspace_rls_observations where name = 'a_membership_delete'), '0', 'A cannot delete its membership');
select is((select value from workspace_rls_observations where name = 'a_workspace_delete'), '0', 'A cannot delete a workspace');
select is((select value from workspace_rls_observations where name = 'a_membership_insert'), '42501', 'A cannot add itself to B workspace');
select is((select value from workspace_rls_observations where name = 'a_workspace_insert'), '42501', 'A cannot create an unprovisioned workspace');
select is((select name from public.workspaces where id = 'a1000000-0000-4000-8000-000000000001'), 'A primary renamed', 'The permitted owner update is persisted');

set local role authenticated;
select set_config('request.jwt.claim.sub', '20000000-0000-4000-8000-000000000002', true);
select set_config(
    'request.jwt.claims',
    '{"sub":"20000000-0000-4000-8000-000000000002","role":"authenticated","aud":"authenticated"}',
    true
);
insert into workspace_rls_observations
values
    ('b_workspaces', (select count(*)::text from public.workspaces)),
    ('b_memberships', (select count(*)::text from public.workspace_memberships)),
    ('b_a_secondary', (
        select count(*)::text from public.workspaces
        where id = 'a2000000-0000-4000-8000-000000000002'
    ));
reset role;

select is((select value from workspace_rls_observations where name = 'b_workspaces'), '2', 'B sees only its own two active workspaces');
select is((select value from workspace_rls_observations where name = 'b_memberships'), '2', 'B sees only its own active memberships');
select is((select value from workspace_rls_observations where name = 'b_a_secondary'), '0', 'B cannot read A-only workspace metadata');

set local role anon;
select set_config('request.jwt.claim.sub', '10000000-0000-4000-8000-000000000001', true);
select set_config(
    'request.jwt.claims',
    '{"sub":"10000000-0000-4000-8000-000000000001","role":"authenticated","aud":"authenticated"}',
    true
);
do $$
begin
    perform count(*) from public.workspaces;
    insert into pg_temp.workspace_rls_observations values ('anon_read', 'not denied');
exception when insufficient_privilege then
    insert into pg_temp.workspace_rls_observations values ('anon_read', '42501');
end $$;
reset role;
select is((select value from workspace_rls_observations where name = 'anon_read'), '42501', 'Client-supplied authenticated claim does not grant the anon database role access');

select * from finish();
rollback;
