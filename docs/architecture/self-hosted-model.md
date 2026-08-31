# Self-hosted AI via Ollama

## Why

The user's original goal, stated early on: *"saya ingin punya ai pribadi tanpa berlanggnan dengan
pihak ketiga"* (a private AI without a third-party subscription). Everything built up to this
point — chat, RAG, tools, agents, the whole Odysseus feature-parity track — ran on
`MODEL_PROVIDER=mock`, a deterministic keyword-matcher with no real reasoning. The gap became
concrete when a real research prompt typed into Chat kept failing to trigger `web.search`, no
matter what tool-calling plumbing got added around it — MockProvider can only match a literal
tool-name word, never real intent. Checked whether adopting Odysseus's own feature set would solve
this (the user's direct question, "kan tadi saya suruh kamu pakai odysseus") — read Odysseus's own
README directly rather than assume, and confirmed it doesn't ship a model either: *"Chat + Agents —
**local/API models**..."* Odysseus is a shell you connect a real model to, architecturally
identical to Krixil. This closes that actual gap.

## What was chosen, and why

**Ollama**, installed natively on Windows (not Dockerized) — recommended earlier for this user's
hardware (Ryzen 7 7840HS / 32GB RAM / RTX 4060 Laptop 8GB VRAM) over vLLM, which targets
datacenter-class GPUs. Native install gives automatic NVIDIA GPU detection with zero Docker
GPU-passthrough configuration. Reached from the `api` container via Docker Desktop's built-in
`host.docker.internal` DNS name.

**Both `qwen2.5:7b` and `llama3.1:8b`**, per the user's explicit choice ("pasang kedua nya nanti
buat saja biar bisa di ganti2 oleh user" — install both, let the user switch), plus
`nomic-embed-text` for embeddings (768-dim, confirmed directly from Ollama's own model metadata).

**No new provider class.** `CloudModelProvider` (`app/ai/cloud_provider.py`) was already documented
as generic "OpenAI-compatible over HTTP... self-hosted vLLM, OpenRouter, etc." — verified directly
against Ollama's own docs that `/v1/chat/completions` supports `tools` (required for both the
Agent loop and Chat's tool-calling) and `/v1/embeddings` is fully supported. Only its constructor
changed, from taking a whole `Settings` object to explicit `(*, name, base_url, api_key, model,
embedding_model)` — so the same class now backs two named providers (`"openai"`, `"ollama"`) with
independent config, `name` moved from a class attribute to instance-level. One existing test
fixture (`tests/test_cloud_provider.py`) updated to match; no behavior change.

## What changed

- **`app/core/config.py`**: `ollama_base_url` (defaults to `host.docker.internal:11434/v1`),
  `ollama_default_model`, `ollama_embedding_model` — dedicated settings, not reusing `openai_*`,
  so real OpenAI-cloud config stays available if ever wanted later.
- **`app/ai/router.py`**: a third `_PROVIDER_FACTORIES` entry, `"ollama"`, using the refactored
  `CloudModelProvider` with a harmless placeholder API key (Ollama ignores the header entirely).
- **`app/ai/catalog.py`**: `get_model_catalog()` is now `async`. When `model_provider == "ollama"`,
  it queries Ollama's own `GET /api/tags` live rather than a hardcoded list — the dropdown always
  reflects exactly what's actually pulled, matching this project's existing "no fabricated catalog
  entries" rule from the original model-listing phase. The embedding model is filtered out (not a
  chat model). `"auto"` always stays present, routing to `ollama_default_model` — this keeps the
  frontend's persisted `selectedModel: "auto"` default working across the provider change with zero
  frontend code needed. `validate_model_id()` is now `async` too; 4 call sites updated
  (`app/ai/models_router.py`, both `chat/router.py` endpoints), all inside already-async functions.
- **`app/chat/router.py`** / **`app/chat/tool_use.py`**: `ChatRequest.model` is now actually
  threaded through to `provider.generate/.stream/.tool_call()` as a `model=` kwarg (skipped for
  `None`/`"auto"`) — `CloudModelProvider` already merged `**kwargs` into its request payload after
  the default `"model"` key (built during the earlier model-listing phase, never wired end-to-end
  since there was only ever one model to switch to before now).
- **Migration `0008_ollama_embedding_dim`**: `nomic-embed-text` outputs 768-dim vectors, not
  OpenAI's 1536 the `document_chunks.embedding` column was originally sized for
  (`0003_documents.py`). Old vectors are from a different model entirely, not just a different
  size — not convertible, only replaceable. **Checked the real database directly before writing
  this**: across all 33 tenants, exactly 4 documents existed, all throwaway artifacts from this
  session's own verification runs; the user's real workspace ("posm") had zero. Safe to truncate
  `document_chunks`/`documents` as part of the resize. Drops and rebuilds the HNSW index too.
- **Frontend: zero code changes.** Confirmed by reading `model-selector.tsx`, `lib/api/models.ts`,
  and `chat-store.ts` first — the dropdown already renders whatever `GET /models` returns, unknown
  ids already fall back to a default icon, and `selectedModel` was already sent on every request.
  Built forward-compatible during the earlier model-listing phase; this is the payoff.

## Verified live (2026-08-31)

`pytest` 101/101 (unaffected — still fully `MockProvider`-driven and hermetic), `ruff`, `mypy`
clean. `alembic upgrade head` applied against the real Postgres; confirmed the column is genuinely
`vector(768)` via `\d document_chunks`. `host.docker.internal:11434` confirmed reachable from
inside the `api` container.

- `GET /models` returns real, dynamically-discovered entries: `auto`, `llama3.1:8b`, `qwen2.5:7b`
  — not a hardcoded list.
- **Real reasoning, not keyword matching**: "What is 17 times 23? Just give me the number." →
  `"391"` (correct). MockProvider could never do this.
- **The actual original failing case, re-tested**: "Research this topic and summarize the key
  points." (with no topic given) got a genuinely sensible clarifying question back — real
  reasoning correctly recognized the request was incomplete, rather than blindly guessing. With a
  concrete topic ("Research the current population of Japan..."), the model independently decided
  to call `web.search` (not `knowledge.search` — no more alphabetical-tiebreak accident) and
  returned a real, well-organized, accurate summary.
- **Real model switching**: same question sent with `model: "llama3.1:8b"` vs `model:
  "qwen2.5:7b"` produced genuinely different behavior — Qwen answered directly and correctly ("I
  am Qwen, a large language model created by Alibaba Cloud"); Llama instead tried repeatedly
  calling `web.search` to answer the same question, hit the `chat_max_tool_calls=3` cap exactly as
  designed, and gave a confused non-answer — a real, legitimate model-behavior difference, not a
  bug, and a good demonstration of why the cap exists.
- Unknown model id → `400`, correctly validated against the live catalog.
- **Real RAG round-trip at the new dimension**: uploaded a document containing a fabricated fact
  ("Krixil's mascot is a robot named Kribo") the model could not know from training, asked about
  it, got the correct answer with a real citation pointing at the right document/chunk — proves
  the full embed → store → retrieve pipeline works genuinely at 768 dimensions, not just that the
  schema migration ran.
- Real SSE streaming confirmed (`chunk` events arriving as real incremental tokens from Ollama).
- Live in the browser (Playwright): model dropdown shows the two real models, tool-call badge
  ("Searched the web") renders for real, the final answer is genuinely researched and
  well-formatted. Zero console/page errors.

## Known, deliberately out of scope

- The conversation header's model label reflects a static per-conversation field set at creation
  (always `"auto"`), not which model actually answered a given message — a pre-existing, cosmetic
  frontend behavior unrelated to this change; the underlying request always uses the real selected
  model correctly, confirmed via direct API tests.
- No reachability/health check is done at Ollama-provider-selection time — an unreachable Ollama
  fails on the first real chat call with a plain connection error, same as the existing `"openai"`
  path already behaves when misconfigured.
