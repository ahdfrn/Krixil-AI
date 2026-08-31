# Odysseus feature-parity track

## Why this track exists

The user asked Krixil to eventually match the feature set of
[Odysseus](https://github.com/odysseus-dev/odysseus) (86k+ stars, a real and popular self-hosted
AI workspace: chat+agents+tools+MCP, deep research, documents, email, notes/tasks/calendar, image
tools, model comparison). Confirmed explicitly after flagging that porting everything at once isn't
realistic — this is a new, ongoing, multi-phase track, same phased discipline as every other
initiative in this project (see [`roadmap.md`](roadmap.md)), not a single build.

## The track

Ordered roughly smallest/most-connected-to-existing-architecture first — only Phase 1 below is
actually designed; the rest are roadmap entries, each gets its own plan when its turn comes:

1. **Web search tool** (done — this doc) — `web.search`, via Tavily.
2. **Deep Research** (done — this doc) — a "Deep research" mode on the Agents page.
3. **2FA** (done — this doc) — self-contained TOTP, no external dependency.
4. **Notes & Tasks** — new CRUD domain, no complex external integration.
5. **Compare** (side-by-side model testing) — only meaningfully different once a second real model
   exists in the catalog (see `phase1.md`'s 2026-08-30 model-listing addendum).
6. **Calendar + reminders** (CalDAV) — real protocol work.
7. **Documents editor** (writing-first, AI-assisted) — a genuine rich-editor feature.
8. **Cookbook** (hardware-aware model recommendations) — curated content/UX.
9. **Image gallery/editor** — needs its own external image-gen/edit API decision.
10. **Email (IMAP/SMTP)** — handles real user credentials, sequenced late deliberately.
11. **MCP support** — a real protocol implementation.

## Phase 1: `web.search` tool

**Provider: Tavily** (`POST https://api.tavily.com/search`, `Authorization: Bearer <key>`) —
purpose-built for AI-agent consumption (clean per-result `title/url/content/score`, plus an
optional synthesized `answer`). Contract confirmed against Tavily's own docs before implementing.

**Config**: `TAVILY_API_KEY` (`app/core/config.py`, `.env.example`) — empty by default. The user
doesn't have a key yet; the tool is built completely and registers itself regardless, exactly like
`CloudModelProvider` already does for `OPENAI_API_KEY` — chat/tools keep working with it unset, and
this specific tool fails with a clear, honest message (`"Web search isn't configured yet — set
TAVILY_API_KEY."`) rather than silently doing nothing or fabricating results.

**`app/tools/web_tools.py`** (new): `WebSearchInput{query, max_results}`, `LOW` risk (read-only, no
approval gate, same tier as `knowledge.search`), `required_permission="web:search"`. Registered via
`app/tools/__init__.py`'s existing side-effect-import list. No new plumbing needed anywhere else —
`app/tools/service.py#_run()` already wraps every handler call in a broad exception handler that
turns any raised error (the missing-key `ValueError`, or an HTTP error from
`response.raise_for_status()`) into `status="failed"` + `error_message=str(exc)`, the same path
every other tool's failures already go through. `GET /tools` and `POST /tools/web.search/execute`
needed zero router changes — both are already generic over whatever's registered.

**Frontend**: `apps/web/src/app/(dashboard)/tools/page.tsx` gets one more hand-written
`ToolForm` case (query input + Run, matching `knowledge.search`'s shape) and a `summarizeOutput()`
case. No other file changed — the tool appears in the Tools page automatically once registered,
since that page already fetches `GET /tools` dynamically.

## Verified live (2026-08-31)

`pytest` 92/92 (2 new: the no-key path fails with the exact expected message; a `respx`-mocked
success path returns correctly trimmed output), `ruff`, `mypy` clean. Frontend `npm run lint` /
`npm run build` clean. Live: registered a tenant, confirmed `web.search` appears on the Tools page
as a 4th tool card, ran it with no key configured, confirmed the execution shows `Failed` with the
exact `TAVILY_API_KEY` message in both a toast and the execution history — the same honest
verification bar as every other phase in this project, applied to the only path actually
verifiable today. Zero console/page errors.

## Real key verified (2026-08-31, same day)

The user provided a real Tavily key shortly after. Set in `services/ai-service/.env` (gitignored,
confirmed via `git check-ignore` before touching it — never went near git), `api` container
rebuilt. Verified for real, not mocked:
- Direct API call (`POST /tools/web.search/execute`, `"what is the capital of France"`) returned
  genuine live results — 3 real sources with real URLs/content/scores, plus a synthesized `answer`
  ("The capital of France is Paris...").
- Same real search run through the actual Tools page UI, execution showed `Completed` with real
  result content, not just the earlier `Failed`/no-key path.
- Ran a real Agent goal ("Search the web for who won the most recent Nobel Prize in Physics...")
  end to end — confirmed the whole loop (`POST /agents/run` → tool call → observation →
  final_response) completes with a real tool invocation in the trace.

**A real bug the Agent-run verification caught**: `apps/web/src/app/(dashboard)/agents/page.tsx`
keyed each step in the trace by `step.step_number` alone — React logged a duplicate-key warning
because the backend's `step_number` deliberately identifies the *loop iteration*, not a unique row
(`app/agents/runner.py`: a `tool_call` and its resulting `observation` are recorded as two separate
`AgentStep` rows sharing one iteration's `step_number` — correct, intentional backend behavior, not
a bug there). Fixed by keying on `${step.step_number}-${step.type}` instead, which is genuinely
unique given the backend's actual data shape. Pre-existing since Web Phase 3, just never triggered
by prior verification because those didn't happen to produce a tool_call step to pair with an
observation in the same recorded run. Re-verified clean after the fix — no console errors.

**Separately, worth knowing but not a bug**: `MockProvider`'s tool-selection is naive keyword
matching (`app/tools/base.py`), and it picked `knowledge.search` instead of `web.search` for a
goal containing the word "search" (both tool names contain that word). This is a pre-existing
MockProvider limitation unrelated to this change — with a real model provider instead of mock, real
reasoning would pick the semantically correct tool. Not fixed here; out of this phase's scope.

## Phase 1 addendum: inline tool-calling in regular Chat

The user tried asking the normal Chat page (not Agents/Tools) to research something and got a
plain "Mock response to: ..." with no search — a real gap, not a misunderstanding: `/chat` and
`/chat/stream` never had any tool access at all, only the separate Agents loop did. Confirmed
("oke lanjutkan") this should be closed rather than requiring a trip to the Agents page for
something as ordinary as "search the web for X" typed straight into Chat.

**Design, not a detour through the Agent loop**: Agents and Chat stay separate systems — Chat has
RAG grounding + short-term memory + real token streaming the Agent loop doesn't share, and an
agent run can take up to 120s across 8 steps, the wrong shape for a conversational reply. Instead
Chat got its own small, bounded, single-turn capability: `app/chat/tool_use.py#run_chat_tools()`
resolves up to `chat_max_tool_calls` (default 3, smaller than `agent_max_tool_calls=5` on purpose)
tool calls synchronously — same message-augmentation loop `app/agents/runner.py` already uses,
reusing `request_tool_execution` — before the final `generate`/`stream` call runs.

**Safety boundary, load-bearing not incidental**: only `RiskLevel.LOW` tools are ever offered to
the model in a chat turn (`knowledge.search`, `usage.get_summary`, `web.search` — never
`document.delete`, `CRITICAL`). Chat resolves tool calls with no human-approval step, so the model
is never even offered a tool that could need one. Tested directly (`test_chat_never_offers_a_
critical_risk_tool`), not just documented in prose.

**Frontend**: `types/chat.ts`'s `ToolCallSummary`/`ToolCallStep` and
`components/chat/tool-call-display.tsx` had sat dormant since Web Phase 1 (built against mock
data, Web Phase 2 documented "no backend event exists for this"). A new SSE event
(`{"type": "tool_calls", ...}`, emitted right where `citations` already is, before any `chunk`)
and matching `ChatResponse.tool_calls` field finally feed them real data — no UI code changed,
`assistant-message.tsx` already rendered `message.toolCalls` unconditionally.

**Not persisted**, matching the existing citations trade-off: reopening an old conversation won't
show what was searched for it.

### Verified live (2026-08-31)

`pytest` 101/101 (+4 new), `ruff`, `mypy` clean. `npm run lint` / `npm run build` clean. `docker
compose up -d --build api` rebuilt. Live: a message containing "usage" correctly triggered
`usage.get_summary` with a real DB-backed result flowing into the model's context (confirmed via
`GET /tools/executions`, not just the chat response's own claim); an ordinary message triggered no
tool (regression check); "please delete this document for me" triggered nothing (the safety
boundary, live not just unit-tested); the SSE stream emitted `tool_calls` before the first `chunk`,
exactly as designed. In the actual browser (Playwright), the tool-call badge rendered for real for
the first time — "✓ Checked your usage summary" — zero console errors.

**The same MockProvider tie-break noted in Phase 1/2 resurfaced here**: a message containing
"search" (e.g. "search the web for...") triggers `knowledge.search`, not `web.search` — both tool
names contain the word "search," and `knowledge.search` sorts first alphabetically in
`list_tools()`, which `MockProvider`'s naive matching always prefers on a tie. This is not a
regression from this change (identical root cause already documented), and it proved the pipeline
itself is real: a genuine LOW-risk tool executed, with real output flowing into context. A real
model provider's actual reasoning (not substring matching) is needed to see `web.search`
specifically triggered from Chat — not yet verified, same open item Phase 1/2 already left.

## Phase 2: Deep Research mode

**No backend change at all.** As predicted when this track was planned: `POST /agents/run` already
runs a full iterative tool-calling loop within a budget, and `web.search` already exists (Phase 1)
— "Deep Research" only needed a frontend affordance that frames a plain question as a
research-shaped goal before sending it through the exact same, unmodified `runAgent()` call the
"Quick task" mode already used.

**`apps/web/src/app/(dashboard)/agents/page.tsx`**: added a `mode: "quick" | "research"` toggle
(two small buttons above the goal textarea, not a new page/route — everything else on this page,
including the run list and detail dialog, is shared and untouched). Research mode changes the
label/placeholder copy and, on submit, wraps the raw question via `buildResearchGoal()`:

> Research the following topic using web search. If one search isn't enough, search again from a
> different angle and cross-reference what you find. Then write a clear, organized report: a short
> summary followed by key findings, citing your sources.
>
> Topic: `{question}`

### Verified live (2026-08-31)

`npm run lint` / `npm run build` clean. Live: confirmed the toggle actually changes the
label/placeholder/button copy, confirmed the *wrapped* goal (not the raw question) is what actually
gets sent and stored — visible verbatim in the run's detail dialog — and confirmed switching back
to Quick task mode is unaffected. Zero console/page errors.

Also ran a real research goal through the whole flow with the real Tavily key from Phase 1 already
configured. It completed cleanly, but — exactly as flagged before running it — `MockProvider`
called `knowledge.search` rather than `web.search` (the same naive-keyword-matching /
alphabetical-tie-break limitation noted above; both tool names contain "search," and
`knowledge.search` sorts first). This isn't a defect in Deep Research mode itself — the toggle, the
goal-wrapping, and the full run lifecycle all worked exactly as designed — it's a ceiling on what's
demonstrable under `MODEL_PROVIDER=mock` specifically. A real model provider's actual reasoning
(rather than substring matching) would correctly choose `web.search` for a research-shaped goal;
that path is not yet verified and needs a real `OPENAI_API_KEY` (or another real provider) to check.

## Phase 3: 2FA (TOTP)

Standard RFC 6238 TOTP, `pyotp` on the backend (pure algorithm, no network calls — genuinely local,
matching the user's original "no third-party subscription" goal more directly than even the search
tool did). QR code rendering happens client-side from the `otpauth://` URI the backend returns
(`qrcode` npm package) — no server-side image generation dependency.

**Schema** (migration `0007_totp`, applied against the real running Postgres, not just SQLite in
tests): `users.totp_secret` (set as soon as setup starts, before confirmation) and
`users.totp_enabled` (only flips true once the user proves possession with a real code — standard
practice, matches how the rest of this project treats "provisioned but not yet proven" state).

**Three new endpoints** (`app/auth/router.py`, all behind the existing `get_current_user`
dependency, no new auth plumbing needed): `POST /auth/2fa/setup`, `POST /auth/2fa/confirm`
(`{code}`, ±30s clock-skew tolerance via `valid_window=1`), `POST /auth/2fa/disable` (`{code}` —
requires a currently-valid code, not just an active session, same reasoning as requiring a password
to change a password). **Login flow**: `LoginRequest` gets an optional `totp_code`; if the account
has 2FA on and it's missing, `401 "2FA code required"`; if present but wrong, `401 "Invalid 2FA
code"` — the frontend distinguishes these by matching the exact detail string (this app's existing
plain-string error convention, not a new structured error-code system).

**Frontend**: `apps/web/src/app/login/page.tsx` reveals a code field on the specific "2FA code
required" response rather than showing it as an error (the password was correct — this is an
expected next step, not a failure). `apps/web/.../settings/page.tsx`'s **Security tab** — previously
a placeholder, now real like every other now-real tab — is the enable/disable UI: QR code + raw
secret fallback + confirm-code field to enable, a confirm dialog requiring a current code to
disable. `useAuthStore` gained `updateUser(patch)` since there's no `/me` endpoint to refetch a
fresh session from after a status-only response (same constraint documented in `web-phase2.md`).

### A real bug this caught: the offline test suite was making live network calls

Running the full `pytest` suite after adding the real Tavily key to `.env` (for Phase 1/2's live
verification) revealed `test_web_search_without_key_fails_with_clear_message` was actually
**succeeding against the real Tavily API** instead of hitting the expected no-key failure path —
`Settings(env_file=".env")` only falls back to the file for anything not already in `os.environ`,
and the test process's `get_settings()` was reading the same real `.env` a developer's live dev
session uses, with no isolation. Fixed in `tests/conftest.py`: `os.environ.setdefault
("TAVILY_API_KEY", "")` and `os.environ.setdefault("MODEL_PROVIDER", "mock")` alongside the
existing `OTEL_ENABLED` override, forcing the same hermetic-regardless-of-local-.env guarantee for
any future secret added there. Not caused by this phase's changes, but only surfaced because this
was the first full-suite run since that real key was added.

### Verified live (2026-08-31)

`pytest` 97/97 (+6 new 2FA tests, using `pyotp.TOTP(secret).now()` for real codes, never a
hardcoded one), `ruff`, `mypy` clean. `alembic upgrade head` applied cleanly against the real
running Postgres. `npm run lint` / `npm run build` clean. Live, full real round-trip with genuinely
computed TOTP codes (a from-scratch RFC 6238 implementation in the verification script itself,
cross-checked against `pyotp` at fixed timestamps before trusting it — not a shortcut, not a
fabricated code): register → enable 2FA (real QR code renders, real secret) → confirm with a
computed code → sign out → log back in, confirm the code-required step appears after a correct
password → submit a computed code → succeeds → disable with another computed code → confirm a
subsequent login no longer asks for one. Zero unexpected console/page errors (the one 401 logged
is the expected response from deliberately submitting without a code first — that's what triggers
revealing the code field, not a bug).
