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
2. **Deep Research** — mostly free once (1) exists and has a real key: the Agent loop
   (`POST /agents/run`) already does iterative tool-calling within a budget, so a research-shaped
   goal against `web.search` already produces multi-step research today. A dedicated UI affordance
   (preset goal template, longer budget) is a light follow-up.
3. **2FA** — self-contained auth hardening (TOTP), no external dependency.
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

**Not yet verified**: a real search actually returning live results. The user doesn't have a
Tavily key yet — once they register for one (free tier, no card required) and set
`TAVILY_API_KEY` in `.env` + rebuild the `api` container, this needs a follow-up live check before
being considered fully done, not just assumed to work because the mocked test passed.
