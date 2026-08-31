# Krixil learns — a new track

## Why this track exists

The user asked whether chatting with Krixil makes it "learn." Honest answer: no —
`qwen2.5:7b`/`llama3.1:8b` are frozen weights, short-term memory only holds context within one
conversation, and RAG only surfaces documents explicitly uploaded. Asked to make it actually learn,
and — offered three genuinely different interpretations (cross-conversation memory, real
fine-tuning, auto-expanding the knowledge base from chat) — the user asked for all three combined.
These differ hugely in complexity and risk, so this is a new, ordered, incremental track, same
discipline as the Odysseus feature-parity track (see `odysseus-parity.md`).

1. **Long-term memory** (done — this doc) — Krixil remembers durable facts about a user across
   *all* their conversations, not just within one.
2. **Auto-expanding knowledge base** — conversations themselves become searchable RAG content, not
   just documents explicitly uploaded. Not yet designed.
3. **Real fine-tuning (LoRA/QLoRA)** — actually retraining the model's own weights periodically.
   Deliberately last: needs a training pipeline that doesn't exist yet, is the most
   hardware-constrained piece on this machine (8GB VRAM), and fine-tuning a small local model on a
   modest amount of personal chat data often doesn't clearly improve it and can measurably hurt
   quality if done carelessly — flagged to the user upfront, before building it, not after. Not
   yet designed.

## Phase 1: Long-term memory

Same pattern `build_rag_context()` (`app/rag/context.py`) already established: a function
returning `ModelMessage | None` to prepend before the model call. New sibling module to
`app/memory/short_term.py`: `app/memory/long_term.py`.

**Extraction**: after each chat turn, a background task asks the model itself to extract durable,
personally-relevant facts as a JSON array (or `[]`) — the same judgment call this assistant applies
to its own memory system. Runs via FastAPI's `BackgroundTasks` for `/chat`, `asyncio.create_task`
(held in a module-level set with a done-callback, the standard fire-and-forget-without-GC pattern)
for `/chat/stream`. The whole body is wrapped in try/except — a malformed response or provider
error just means nothing gets remembered from that turn, never a crash.

**A privacy toggle from day one**: `users.memory_enabled` (default `true`) gates both extraction
and retrieval. New `app/memory/router.py`: `GET/POST /memory`, `DELETE /memory/{id}`,
`GET/PATCH /memory/settings`. New Settings → Memory tab (was already a placeholder section name,
same "close the dormant gap" situation Chat's tool-call UI was in before).

### A real, load-bearing bug this caught live, not in review

**FastAPI does not guarantee `BackgroundTasks` run after a `yield`-dependency's own commit.**
`source_conversation_id` was originally a real foreign key to `conversations.id` — reasonable on
paper (traceability), but the very first live chat test threw a `ForeignKeyViolationError`: the
background extraction task tried to insert a `UserMemory` row referencing a `Conversation` row
that hadn't been committed yet by the *same request* that triggered the background task. This
isn't a SQLite quirk — it happened against the real Postgres container. Fixed by making
`source_conversation_id` a plain, unconstrained UUID column — it was already documented as
"traceability only, not a hard dependency," so dropping the FK (rather than adding retry/ordering
logic) was the right-sized fix, not a workaround. Since this migration had only existed for
minutes in the same session (never committed to git), it was edited directly and re-cycled
(`alembic downgrade -1` → `upgrade head`) rather than layered with a second fixup migration.

**The same underlying ordering issue also broke the offline test suite** in a second, different
way: `tests/conftest.py` used `:memory:` SQLite + `StaticPool`, which hands every session the
*exact same physical connection*. The background task's own session (opened via
`app.memory.long_term.AsyncSessionLocal`, patched to the same `session_factory` as the main
request) ran on that same shared connection while the main request's session hadn't committed yet;
when the background task's session then rolled back (MockProvider's non-JSON response failing to
parse), it rolled back the *main* session's still-uncommitted `Conversation`/`Message` inserts too
— confirmed by directly querying the DB mid-test (the row was provably gone right after the
background task ran). Fixed by switching the test engine fixture from `:memory:` + `StaticPool` to
a temp *file*-backed SQLite database with normal connection pooling — each session gets its own
real connection with proper transaction isolation, matching how separate Postgres connections
actually behave in production (where this specific corruption was never possible). Also had to add
`app.memory.long_term.AsyncSessionLocal` to `conftest.py`'s monkeypatch list, mirroring the
existing `app.chat.router.AsyncSessionLocal` patch — the background task's independent session
needed its own patch target to land on the test database at all.

### Verified live (2026-08-31)

`pytest` 107/107 (+6 new), `ruff`, `mypy` clean. `alembic upgrade head` applied against the real
Postgres (re-cycled once after the FK fix). Live, with the real Ollama-backed `qwen2.5:7b`:
- A conversation stating a name and project ("Nama saya Fehri, saya sedang membangun... Krixil
  AI") produced two real, correctly-extracted `UserMemory` rows.
- A **brand-new, separate conversation** (zero prior messages, so short-term memory has nothing to
  offer) correctly answered "What is my name?" — proving the injected context is genuinely
  long-term, not just conversation-local. ("You mentioned that your name is Fehri in our previous
  conversation... your platform AI named Krixil AI.")
- Toggling memory off and re-asking the same question correctly got no recall (the model
  genuinely didn't know); toggling back on restored it.
- Deleting a fact via the Settings UI removed it from both the list and future context.
- Manually adding a fact via the Settings UI worked and was immediately usable.
- Zero console/page errors (Playwright).

**Also worth knowing, not a bug**: one live response came back with garbled/mixed-script text
(Indonesian mixed with stray CJK-looking characters) on a longer, mixed-language prompt — a
one-off `qwen2.5:7b` model-quality glitch (reproduced once, not consistently — a follow-up
question with a cleaner, English phrasing answered correctly and coherently). Extraction still ran
on that garbled response and stored an equally garbled fact, a downstream consequence, not a
separate bug in the extraction code itself.

## Phase 2: Auto-expanding knowledge base

Conversations themselves become searchable RAG content, not just documents explicitly uploaded —
so a later question like "what did we decide about X?" can surface real past discussion, not just
personal facts about the user.

**Maximum reuse of the existing RAG pipeline.** `hybrid_search()` and `build_rag_context()`
already operate generically over `DocumentChunk` rows joined to their owning `Document` — neither
cares whether a `Document` came from a real upload or was auto-created from a conversation. So
this phase is fundamentally: get conversation content into `DocumentChunk` rows the same shape
uploaded documents already produce. `Document` gained a `source` discriminator
(`"upload" | "conversation"`) and a soft-reference `source_conversation_id` (migration
`0010_document_source`) — one growing document per conversation (found by
`source_conversation_id`, chunks appended continuing from the current `chunk_count`), not one per
turn. No real file backs a conversation-sourced document — `app/rag/conversation_ingest.py`'s
`ingest_conversation_turn()` skips `storage.upload()` entirely and uses a sentinel `storage_key`;
confirmed safe since `MinioObjectStorage.delete()` already swallows `NoSuchKey`.

**Reuses Phase 1's own extraction call, extended rather than duplicated.** Running a second LLM
judgment per turn just to decide "is this worth indexing" would double background-task cost for
no good reason — so `_EXTRACTION_SYSTEM_PROMPT` (`app/memory/long_term.py`) now asks for two
things in one call: `"memories"` (personal facts, unchanged from Phase 1, shown in Settings) and
`"notes"` (decisions, explanations, or details worth searching later, even if not personally
about the user). Either being non-empty triggers indexing the raw turn.

### Two more real bugs, both live-testing catches — before jumping to "auto-indexing must be broken"

**The first attempt looked broken but wasn't a pipeline bug** — the very first live test (a real
technical decision: "use PostgreSQL with pgvector, Redis for caching") produced *no* document at
all. Cause: the extraction prompt at that point was still scoped to Phase 1's original wording
("personal facts about the user") — a project's tech-stack decision correctly, faithfully didn't
qualify under that literal wording. This directly motivated the two-category prompt redesign
above rather than accepting it as a documented limitation, since it went to the actual stated
purpose of this phase.

**The second attempt looked broken too, and this time it really was a bug** — after fixing the
prompt, a `UserMemory` row was created correctly, but still no `Document`. Root cause: a second
instance of the exact same background-task race Phase 1 already hit once (FastAPI doesn't
guarantee `BackgroundTasks` run after the triggering request's own session commits). This
function added a *fresh* `select(Conversation)` query inside the background task to get the
conversation's title — and for a brand-new conversation, that row sometimes isn't committed yet
when the background task runs, so the query silently found nothing and skipped indexing with no
error logged (worse than Phase 1's version of this bug, which at least threw loudly). **Fixed** by
not reading the `Conversation` row from a separate session at all: `ingest_conversation_turn()`
now takes `conversation_id`/`conversation_title` as plain values, threaded through from the
in-memory `Conversation` object the triggering request already has — the same reason
`user_message`/`assistant_message` were already passed as plain strings instead of re-queried.
**Lesson reinforced**: any background task in this codebase must treat *every* piece of data from
its triggering request as something that might not be visible in the database yet, not just the
one field that happens to have a foreign key pointed at it.

### Verified live (2026-08-31)

`pytest` 110/110 (+4 new — `hybrid_search` itself has no offline coverage anywhere in this suite,
same reason: `cosine_distance` is a Postgres-only pgvector operator), `ruff`, `mypy` clean.
`alembic upgrade head` applied against the real Postgres. Live, with the real Ollama model:
- A technical-decision conversation ("use PostgreSQL with pgvector, Redis for caching") produced a
  real `Document` (`source="conversation"`, 2 chunks) — correctly *not* a `UserMemory` entry,
  since it isn't a personal fact.
- `hybrid_search` genuinely found it via the Knowledge page's search — real chunks, real
  relevance scores.
- **The actual end-to-end goal, proven**: a brand-new, separate conversation asked "What database
  did we decide to use for the Krixil project?" and got a correct, coherent answer with two real
  citations pointing at the conversation-sourced document — cross-conversation knowledge retrieval
  working exactly as designed.
- Deleting the conversation-sourced document succeeded cleanly (204) despite no real file ever
  existing behind it.
- Toggling memory off correctly blocked a new discussion-worthy exchange from creating any new
  document.
- Live in the browser: the Knowledge page renders conversation-sourced entries with a distinct
  `MessageSquare` icon and a "From a conversation" label instead of a file size. Zero console
  errors.

**Also worth knowing, not a bug, recurring rather than one-off now**: the raw indexed content from
one turn came back visibly garbled (mixed Indonesian + stray CJK-looking characters) when searched
— the same `qwen2.5:7b` mojibake glitch first seen in Phase 1, now confirmed to recur specifically
on longer, technical Indonesian responses rather than being a rare fluke. Not a pipeline defect —
the ingestion/search machinery faithfully stored and retrieved exactly what the model generated,
garbled or not. Worth keeping an eye on if it keeps happening; not something this phase's code can
fix.

## Phase 3: Autonomous fine-tuning ("belajar mandiri")

The user asked for the last, most consequential piece explicitly: real fine-tuning, and for it to
happen **on its own** — not a one-off manual command. Flagged from the start of this whole track
as needing real care, and confirmed for real before designing anything: the user's actual tenant
had 27 real turns at the time this was scoped, checked against Unsloth's own documented guidance
(fetched live) of "a bare minimum of at least 100 rows... over 1,000 preferable." This phase isn't
"wait and don't build it" — it's the opposite: the entire autonomous pipeline is built and running
for real, gated on a real data-readiness check, so it does nothing premature yet and starts firing
on its own the moment there's enough real usage.

### Design

**Reuses the existing RAG/hybrid-search-style discipline of maximal reuse.** The dataset comes
straight from real `Message` history (`app/finetune/dataset.py`), gated by the same
`users.memory_enabled` toggle Phases 1-2 already use — one privacy switch, not a third one to
explain. The safety gate reuses the *existing* evaluation harness from the original backend
Phase 5 (`run_evaluation_suite()`) rather than a new one: a candidate fine-tuned model only gets
promoted (renamed to a real, permanent Ollama tag, appearing as one more selectable model
alongside the base ones) if it doesn't regress against the current baseline on that suite. A
regression gets `ollama rm`'d immediately — never visible to select from, not even briefly.

**A new, separate `training/` project, not part of `services/ai-service`.** PyTorch+CUDA, Unsloth,
transformers, peft, trl are large, CUDA-specific dependencies that have no business in the
always-running `api` container. `training/` runs **natively on Windows** — real QLoRA fine-tuning
needs actual GPU access, the same reason Ollama itself runs natively rather than inside Docker.
It talks to the containerized `api` service over plain HTTP, reusing its existing auth entirely
(a real login, not a new service-account system) rather than opening its own database connection.

**A real design correction made during implementation, not before.** The original plan had the
`api` container's own lifespan launching `training/` as a subprocess on a schedule. That can't
actually work — a Linux container cannot spawn a process with the Windows host's GPU access, full
stop. Fixed by reversing the direction: `training/scheduler.py` is the actual "mandiri" loop, a
long-running native process that polls the `api` service periodically for real readiness or a
pending manual request, and runs the pipeline locally when either is true. The `api` side only
ever records state (dataset export, evaluation verdicts, run history via the new `finetune_runs`
table) — it never spawns or is spawned by the other side.

**Model-loading and dataset formatting verified live against Unsloth's own current docs and
example notebooks before writing any code** — not assumed from training data that could be stale:
`FastLanguageModel.from_pretrained`/`get_peft_model` parameters, and critically, using the base
instruct model's own `tokenizer.apply_chat_template()` rather than a hand-picked template name —
Unsloth's own docs flag an incorrect chat template as the most common cause of a GGUF-exported
model underperforming in Ollama versus in Unsloth itself.

### A real install detour, caught before it caused a mess

Unsloth's own docs advertise a one-line Windows installer
(`irm https://unsloth.ai/install.ps1 | iex`) — fetched and read its actual contents before running
it (never pipe an unread script), and it turned out to install a **separate desktop IDE
application** ("Unsloth Studio") with its own managed environment, registry PATH changes, and a
completely different venv location than `training/.venv`. Not what this project wants. Used plain
`pip install unsloth` instead. That pulled in a **CPU-only** torch build by default — caught
immediately by checking `torch.cuda.is_available()` rather than assuming success — fixed by
installing the exact CUDA-matched version from PyTorch's own index
(`torch==2.11.0+cu126`, matched to Unsloth's `torch<2.12.0` ceiling and this GPU's driver-reported
CUDA 13.1 capability), confirmed against the real RTX 4060 Laptop GPU afterward.

### Verified live (2026-08-31)

`pytest` 118/118 (+8 new), `ruff`, `mypy` clean. `alembic upgrade head` applied against the real
Postgres. Backend endpoints verified live end-to-end with a fresh test tenant: dataset export
returns real message pairs (filtered correctly by length and the memory toggle), the readiness
gate correctly reports not-ready against real data below the threshold, a manual trigger creates a
real tracked run, `/finetune/evaluate` genuinely runs the existing evaluation harness against a
real Ollama model over the real Postgres-backed cases (5 passed, 0 failed, `regression: null` — no
prior baseline yet, exactly the documented behavior for a first run) — not simulated. Settings →
Fine-tuning tab live-verified in the browser: real readiness progress, a correctly-disabled "Run
now" button below the threshold, zero console errors.

**The full native pipeline** — `training/`'s own venv, real Unsloth QLoRA fine-tuning, GGUF
export, Ollama registration, evaluation-gated promotion — was set up and run for real against a
temporarily-lowered threshold (a handful of real messages from a fresh test tenant, reverted
immediately after) to prove the mechanism genuinely works end to end, not just that each piece
looks right in isolation.

### The full run: 9 real failures, then a genuine end-to-end success

Ten attempts, every one of them tracked as a real `finetune_runs` row (nothing hidden or
retried silently) — each failure was a real, fixable gap, not a flaw in the design:

1. `SFTTrainer.__init__() got an unexpected keyword argument 'tokenizer'` — the installed `trl`
   (0.24.0) renamed this to `processing_class`, and moved `dataset_text_field`/`max_seq_length`
   (also renamed to `max_length`)/`packing` from `SFTTrainer`'s own constructor onto `SFTConfig` —
   checked the installed version's real signature via `inspect.signature` and fixed against that,
   not the reference notebook's older API shape.
2–4. **A missing system toolchain, one tool at a time**: `cmake`, then MSVC Build Tools
   (`cl.exe`), then `openssl` — each needed to build `llama.cpp` from source after Unsloth's
   prebuilt binary download failed for an unrelated packaging quirk (a stray Svelte UI file path
   inside its zip). Installed each via `winget` as the error messages themselves suggested,
   loading the MSVC developer environment into the session via `vcvarsall.bat` since PowerShell
   doesn't pick up new PATH entries from an installer mid-session.
5. A transient Windows file-lock on a stale `~umpy.libs` temp directory from an earlier attempt —
   cleaned up, not a real dependency problem.
6. **The actual GGUF file wasn't where the code looked for it** — Unsloth's
   `save_pretrained_gguf(path, ...)` writes to `f"{path}_gguf"`, not `path` itself, undocumented
   anywhere checked beforehand and only found by inspecting a real successful run's actual output
   on disk.
7–9. **Registering the fine-tuned model with Ollama** took three real attempts: first, a bug in
   this project's own code preserved none of the failure artifacts (cleanup ran even on
   exceptions), making the actual error opaque — fixed by only cleaning up on success. Second, a
   genuinely wrong assumption about Ollama's current `/api/create` HTTP contract: it now requires
   the GGUF pre-uploaded as a content-addressed blob, not a `FROM <path>` Modelfile string the way
   the CLI itself still accepts — checked live against Ollama's own current API docs after the
   real 400 error, rather than guessing a second time. Fixed by shelling out to the real `ollama`
   CLI (`ollama create <tag> -f <modelfile-path>`) instead of reimplementing blob upload by hand —
   simpler and more robust since `training/` already runs natively on the same machine Ollama
   does, and it's the exact path Unsloth's own printed instructions point at.

**The tenth attempt succeeded completely, for real**: trained a real LoRA adapter (loss 0.9211,
real gradient descent on the actual RTX 4060 Laptop GPU), merged and exported a genuine
q4_k_m-quantized GGUF, registered it with Ollama as `krixil-candidate-*`, ran it through the real
evaluation harness (5 passed, 0 failed against the real Postgres-backed cases), and — not
regressing — promoted it to `krixil-personalized-2026-08-31`, which then appeared as a real,
additional entry in `GET /models` alongside the base models. Sent it a real chat message through
Krixil's own `/chat` endpoint by explicitly selecting it and got a coherent response with real RAG
citations — the exact same code path an end user would go through picking it from the dropdown.
Removed afterward since it was trained on throwaway test conversations, not real usage — the
mechanism was what needed proving, not that specific model.

### Known, deliberate trade-off

A training run and live Ollama chat share the same GPU — chat is noticeably slower while a
fine-tune is running. Reasonable for a personal, single-user tool; not addressed with a
time-of-day scheduling window in this version.
