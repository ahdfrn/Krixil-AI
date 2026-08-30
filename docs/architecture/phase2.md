# Phase 2 — RAG

## Pipeline

```
Upload → extension/size validation → parse (pdf/docx/txt/csv) → clean → chunk (char-based,
overlap) → embed (ModelProvider.embeddings(), batched) → store (documents + document_chunks,
raw file in MinIO)
```

Runs synchronously inside the upload request — no background job queue yet. Fine for the
expected document sizes now; the natural upgrade if that changes is a queue (Celery/RQ) consuming
the same `ingest_document()` function, not a rewrite of it.

## Search

`hybrid_search()` (`app/rag/search.py`) runs two ranked lists and merges them with reciprocal
rank fusion (RRF, k=60 — the standard default, not tuned):

- **Vector**: `document_chunks.embedding.cosine_distance(query_embedding)`, backed by an HNSW
  index (`vector_cosine_ops`).
- **Keyword**: Postgres full-text (`to_tsvector('english', content) @@ plainto_tsquery(...)`),
  backed by a GIN index on the same expression (no stored tsvector column — computed inline;
  fine at Phase 2 corpus sizes, a materialized column is a self-contained upgrade later).

RRF over a cross-encoder reranker: no extra model to serve, well-established merge technique,
good enough for now — a real reranker slots in behind the same `hybrid_search()` signature later.

Before running either query, `_tenant_has_chunks()` does a cheap existence check and returns `[]`
immediately if the tenant has no documents — this is what keeps `/chat` safe to call
unconditionally for every tenant (see below) and is also just the right thing to do (no point
running a vector query against an empty KB).

## `EmbeddingVector` — the portable column type

pgvector's `vector(dim)` only exists on Postgres. `app/db/vector_type.py` wraps it in a
`TypeDecorator` that's `vector(dim)` on Postgres and a plain JSON array on other dialects (SQLite,
used by the offline test suite) — so chunk storage is testable everywhere, while similarity
search stays exactly what production actually runs, not an approximation. One non-obvious bit:
`TypeDecorator` does **not** inherit the impl's custom comparator methods automatically, so
`cosine_distance`/`l2_distance`/`max_inner_product` are redeclared explicitly on
`EmbeddingVector.comparator_factory` (same pgvector operators pgvector.sqlalchemy.Vector itself
uses) — verified against the real Docker stack, since this is exactly the kind of thing that looks
right and silently isn't.

`EMBEDDING_DIMENSION` defaults to 1536 (OpenAI `text-embedding-3-small`'s size) so switching
`MODEL_PROVIDER` from `mock` to `openai` needs no config change. `MockProvider.embeddings()`
reads the same setting and produces deterministic, text-dependent fake vectors of that size, so
the default (`mock`) path works out of the box too.

## RAG-augmented chat

`/chat` and `/chat/stream` call `build_rag_context()` before generating. For a tenant with no
documents this is a no-op (see `_tenant_has_chunks` above) — confirmed this doesn't touch the
Postgres-only search query at all, which is what keeps the whole existing offline chat test suite
(written before RAG existed) green on SQLite. When there are relevant chunks, they're injected as
a system message and returned as `citations` in `ChatResponse` (streaming: a `citations` SSE event
before the content chunks).

## What's offline-testable vs. live-only

Chunking, parsing (pdf/docx/txt/csv), and the document upload/list/delete API flow (via a
`FakeObjectStorage` test double) are covered by the offline pytest suite. Hybrid search itself —
`cosine_distance`, `to_tsvector`/`ts_rank` — is Postgres-specific and cannot run against SQLite;
it's verified live against the real Docker stack instead: real upload → hybrid search returning
correct results → RAG-augmented chat producing citations → tenant-without-documents chat still
working → delete cascading through both Postgres (FK `ON DELETE CASCADE`) and the MinIO object.

## Config added

`EMBEDDING_DIMENSION`, `RAG_CHUNK_SIZE`, `RAG_CHUNK_OVERLAP`, `RAG_TOP_K`, `MAX_DOCUMENT_SIZE_MB`.

## Verified

Offline suite: 51/51 tests pass. Live in Docker: uploaded a real .txt document, confirmed
`vector(1536)` column + HNSW + GIN indexes exist as migrated, hybrid search returned the right
chunk for a semantic query, `/chat` on that tenant returned an answer with a matching citation,
`/chat` on a document-less tenant returned `citations: []` with no error, and deleting the
document removed both the Postgres rows (cascaded to `document_chunks`) and the MinIO object.
