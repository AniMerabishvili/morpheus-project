-- Morpheus production security baseline.
-- Run this in Supabase SQL Editor after backing up the project.

begin;

-- Required ownership column for per-user dream isolation.
alter table public.dreams
  add column if not exists user_id uuid references auth.users(id) on delete cascade;

-- Enable RLS on all app data tables.
alter table public.dreams enable row level security;
alter table public.dream_keywords enable row level security;
alter table public.keywords enable row level security;
alter table public.knowledge_base enable row level security;

-- Keep RLS active even for table owners. Supabase service-role still bypasses
-- RLS by design and must remain server-only.
alter table public.dreams force row level security;
alter table public.dream_keywords force row level security;
alter table public.keywords force row level security;
alter table public.knowledge_base force row level security;

-- Remove older policies so this migration is idempotent.
drop policy if exists "Users can view own dreams" on public.dreams;
drop policy if exists "Users can insert own dreams" on public.dreams;
drop policy if exists "Users can update own dreams" on public.dreams;
drop policy if exists "Users can delete own dreams" on public.dreams;

drop policy if exists "Users can view own dream keyword links" on public.dream_keywords;
drop policy if exists "Users can insert own dream keyword links" on public.dream_keywords;
drop policy if exists "Users can update own dream keyword links" on public.dream_keywords;
drop policy if exists "Users can delete own dream keyword links" on public.dream_keywords;

drop policy if exists "Users can view keywords linked to own dreams" on public.keywords;

drop policy if exists "Authenticated users can read knowledge base" on public.knowledge_base;

-- dreams: every row must belong to the authenticated user.
create policy "Users can view own dreams"
on public.dreams
for select
to authenticated
using (auth.uid() = user_id);

create policy "Users can insert own dreams"
on public.dreams
for insert
to authenticated
with check (auth.uid() = user_id);

create policy "Users can update own dreams"
on public.dreams
for update
to authenticated
using (auth.uid() = user_id)
with check (auth.uid() = user_id);

create policy "Users can delete own dreams"
on public.dreams
for delete
to authenticated
using (auth.uid() = user_id);

-- dream_keywords: relation rows are visible/writable only through a dream
-- owned by the authenticated user.
create policy "Users can view own dream keyword links"
on public.dream_keywords
for select
to authenticated
using (
  exists (
    select 1
    from public.dreams d
    where d.id = dream_keywords.dream_id
      and d.user_id = auth.uid()
  )
);

create policy "Users can insert own dream keyword links"
on public.dream_keywords
for insert
to authenticated
with check (
  exists (
    select 1
    from public.dreams d
    where d.id = dream_keywords.dream_id
      and d.user_id = auth.uid()
  )
);

create policy "Users can update own dream keyword links"
on public.dream_keywords
for update
to authenticated
using (
  exists (
    select 1
    from public.dreams d
    where d.id = dream_keywords.dream_id
      and d.user_id = auth.uid()
  )
)
with check (
  exists (
    select 1
    from public.dreams d
    where d.id = dream_keywords.dream_id
      and d.user_id = auth.uid()
  )
);

create policy "Users can delete own dream keyword links"
on public.dream_keywords
for delete
to authenticated
using (
  exists (
    select 1
    from public.dreams d
    where d.id = dream_keywords.dream_id
      and d.user_id = auth.uid()
  )
);

-- keywords: this is a shared dictionary, so normal users may only read symbols
-- that are connected to their own dreams. Inserts/updates/deletes are handled by
-- the server-side service-role helper and have no authenticated-user policy.
create policy "Users can view keywords linked to own dreams"
on public.keywords
for select
to authenticated
using (
  exists (
    select 1
    from public.dream_keywords dk
    join public.dreams d on d.id = dk.dream_id
    where dk.keyword_id = keywords.id
      and d.user_id = auth.uid()
  )
);

-- knowledge_base contains static academic chunks, not user content. It is
-- readable only by signed-in users so anon-key-only clients cannot query it.
create policy "Authenticated users can read knowledge base"
on public.knowledge_base
for select
to authenticated
using (auth.uid() is not null);

-- Function used by RAG retrieval. SECURITY INVOKER keeps RLS in effect.
-- NOTE: search_path includes `extensions` because Supabase installs the
-- pgvector extension (and its <=> operator) into the `extensions` schema,
-- not `public`. Without this, the <=> operator cannot be resolved at runtime.
create or replace function public.match_documents (
  query_embedding extensions.vector(384),
  match_threshold float,
  match_count int
)
returns table (
  id uuid,
  book_title text,
  content text,
  similarity float
)
language sql
stable
security invoker
set search_path = public, extensions
as $$
  select
    knowledge_base.id,
    knowledge_base.book_title,
    knowledge_base.content,
    1 - (knowledge_base.embedding <=> query_embedding) as similarity
  from public.knowledge_base
  where 1 - (knowledge_base.embedding <=> query_embedding) > match_threshold
  order by knowledge_base.embedding <=> query_embedding
  limit match_count;
$$;

grant usage on schema public to authenticated;
grant select, insert, update, delete on public.dreams to authenticated;
grant select, insert, update, delete on public.dream_keywords to authenticated;
grant select on public.keywords to authenticated;
grant select on public.knowledge_base to authenticated;
grant execute on function public.match_documents(extensions.vector, float, int) to authenticated;

commit;