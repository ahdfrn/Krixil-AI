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
