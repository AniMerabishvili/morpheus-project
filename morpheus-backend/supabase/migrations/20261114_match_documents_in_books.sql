-- Book-filtered RAG retrieval: same as match_documents, restricted to the
-- books the dreamer selected (knowledge_base.book_title values).
begin;

create or replace function public.match_documents_in_books (
  query_embedding extensions.vector(384),
  match_threshold float,
  match_count int,
  book_titles text[]
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
  where knowledge_base.book_title = any(book_titles)
    and 1 - (knowledge_base.embedding <=> query_embedding) > match_threshold
  order by knowledge_base.embedding <=> query_embedding
  limit match_count;
$$;

grant execute on function public.match_documents_in_books(extensions.vector, float, int, text[]) to authenticated;

commit;
