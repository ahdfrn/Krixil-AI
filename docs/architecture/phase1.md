# Phase 1 — Real model provider + memory

## What was added

- **`CloudModelProvider`** (`app/ai/cloud_provider.py`): OpenAI-compatible HTTP client behind the
  same `ModelProvider` ABC as `MockProvider`. Registered in `ModelRouter` under `"openai"`, built
  lazily (only constructed — and its httpx connection pool only opened — if actually selected via
  `MODEL_PROVIDER=openai`), closed on app shutdown via `app.ai.router.aclose_providers()`.
  `tool_call()` still raises `NotImplementedError`, matching `MockProvider` — `ModelResponse` has
  no field for structured tool calls yet, and there's no caller until the Tool System phase; that's
  when both get extended together instead of guessing the shape now.
- **Short-term memory** (`app/memory/short_term.py`): a Redis-backed cache of each conversation's
  recent message window, used to build the context sent to the model. Postgres (`list_messages`)
  stays the durable source of truth — a cache miss (cold start, evicted key, expired TTL) costs one
  extra DB read and repopulates the cache; it never loses or corrupts history. Every write path
  (`/chat`, `/chat/stream`) writes through to both Postgres and Redis.
- **Per-tenant rate limiting** (`app/core/rate_limit.py`): fixed 60-second window, Redis `INCR` +
  `EXPIRE`, keyed by `tenant_id`, shared across `/chat` and `/chat/stream`. Trade-off: a fixed
  window can let a burst of up to ~2x the configured limit through right at a minute boundary —
  acceptable for Phase 1 (this is about stopping a runaway/misbehaving client, not precise quota
  billing); a sliding-window upgrade is a self-contained follow-up if that ever matters.
- **Usage tracking** (`usage_records` table, migration `0002_usage_records`): every non-streaming
  `/chat` call records `tenant_id`, `user_id`, `conversation_id`, `model`, `prompt_tokens`,
  `completion_tokens`. `/chat/stream` does not yet — most OpenAI-compatible streaming responses
  don't include a usage payload unless a provider-specific option is set, so non-streaming `/chat`
  is the accurate source for usage in this phase.

## Config added

`OPENAI_BASE_URL`, `OPENAI_MODEL`, `OPENAI_EMBEDDING_MODEL` (provider), `SHORT_TERM_MEMORY_MAX_MESSAGES`,
`SHORT_TERM_MEMORY_TTL_SECONDS` (memory), `RATE_LIMIT_CHAT_PER_MINUTE` (rate limit). All have
working defaults — nothing here is required to keep running with `MODEL_PROVIDER=mock`.

## Verified

Offline suite: 29/29 tests pass (`CloudModelProvider` tested against a mocked HTTP transport via
`respx` — no real API key or network needed). Also verified live against the real Docker stack:
migration applied cleanly on top of existing Phase 0 data, a real chat call populated the expected
`krixil:short_term:*` and `krixil:ratelimit:chat:*` Redis keys, and wrote a matching row to
`usage_records` in Postgres.

## Addendum (2026-08-30): conversation rename & delete

Added after all 6 original phases were complete, prompted by the web app's frontend having had
Rename/Delete UI since Web Phase 1 with nothing real to call. `PATCH /conversations/{id}`
(`ConversationRenameRequest{title}`) and `DELETE /conversations/{id}` in `app/chat/router.py` /
`service.py`, no schema change needed (`title` already existed; `Message.conversation_id` already
had `ondelete="CASCADE"`, mirroring `rag/documents.py`'s `delete_document` pattern exactly). No new
permission gate — conversations were never behind the Tool System's approval model, matching how
documents' own REST delete route works.

While extending `get_conversation_or_404` for these, tightened it to also filter by
`Conversation.user_id` (previously tenant-only) — it now matches `list_conversations`'s existing
per-user scoping, closing a real gap where any user in a tenant could read/act on another user's
conversation by id. This also affects `GET /conversations/{id}` and the `conversation_id` passed to
`/chat`/`/chat/stream`. Not covered by an automated test: same-tenant-different-user isolation —
there's no way to create a second user in one tenant via the API yet (registration always creates a
new tenant), so that scenario isn't constructible through the real API surface without either raw
DB manipulation in a test or an invite/add-user endpoint, which is separate, larger scope.

Frontend: `apps/web`'s Rename/Delete menu items (in `chat-header.tsx` and `chat-history-item.tsx`)
now call these endpoints for real, with optimistic local updates that roll back on failure. Pin and
Archive are unchanged — still "not available yet" toasts, since they'd need new DB columns.

Verified: `pytest` (85/85, +6 new tests), `ruff`, `mypy` all clean. Live: renamed a conversation via
both the header and the sidebar item and confirmed it survived a reload (real backend truth, not
local state); deleted the open conversation, confirmed navigation to `/chat`, and confirmed after a
reload it was genuinely gone (not just removed from local state) while the untouched conversation
remained; confirmed Pin/Archive still show their unchanged stub toast. Zero console/page errors.

## Addendum (2026-08-30): real model listing + per-request model field

Closes the other half of what the web app's frontend has faked since Web Phase 1: a 5-option model
selector (Auto/Fast/Reasoning/Coding/Research) backed by nothing. The real constraint:
`ModelRouter.get_provider()` (`app/ai/router.py`) only ever resolves **one** active provider, chosen
once at startup by `MODEL_PROVIDER` — there's no backend concept of multiple simultaneously
available models. Confirmed with the user: expose exactly what's real (one model) rather than
fabricate variants, shaped so a second real model slots in later without another frontend change.

Added `app/ai/catalog.py` (`get_model_catalog()` — today always one entry, `id="auto"`, with a
`description` computed live from the active config, e.g. "Routes to gpt-4o-mini via the configured
OpenAI-compatible endpoint" or the mock-provider equivalent; `validate_model_id()` — 400s on an
unrecognized id, no-ops on `None`), `app/ai/models_router.py` (`GET /models`, authenticated like
every other route here), and `model: str | None = None` on `ChatRequest`, validated at the top of
both `/chat` and `/chat/stream` before any DB work (validated outside the SSE generator for
`/chat/stream` specifically, so a bad model id gets a real 400 instead of a 200-with-error-event).
`CloudModelProvider.generate`/`stream`/`tool_call` already merge `**kwargs` into the outgoing
payload after the default `"model"` key, so passing `model=...` through already overrides it for
free — no provider-level change needed for when a second real model exists to route to.

Frontend: `lib/api/models.ts` now calls the real endpoint instead of returning mock data; the
now-fully-dead `src/lib/mock/` directory (models/conversations/responses — the last of it was still
referenced by the old `listModels()`) was deleted, a Phase 2 cleanup that had been missed.
`selectedModel` (already defaulted to `"auto"`) is now actually sent in chat requests instead of
being computed and discarded. Visible effect, not a bug: the model dropdown shrinks from 5 mock
entries to 1 real one — the honest result of the option chosen, not a regression.

Verified: `pytest` (90/90, +4 new tests: `GET /models` returns one `id="auto"` entry and requires
auth; `POST /chat` accepts `model:"auto"` and rejects `model:"nonsense"` with 400, both streaming
and non-streaming), `ruff`, `mypy` clean. Live: the dropdown shows exactly one real entry (not the
old 5) in both the composer and an open conversation's header, with a description that genuinely
reflects live config; captured the real outgoing `/chat/stream` request and confirmed
`model:"auto"` actually rides in the body; sending a message still streams and renders correctly.
Zero console/page errors.
