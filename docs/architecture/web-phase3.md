# Web app — Phase 3 (Knowledge, Tools, Agents pages + Settings Usage/Account)

## Scope

Replaces the `/knowledge`, `/agents`, `/tools` placeholder pages and 2 of `/settings`'s 10 tabs
with real pages wired to the backend systems that already exist for them — same discipline as
Phases 1–2: read the actual route/schema source first, scope to what's really implemented.

## Confirmed real backend contract

- **Tools** (`GET /tools`, `POST /tools/{name}/execute`, `GET /tools/executions`,
  `POST /tools/executions/{id}/approve|reject`): exactly 3 tools exist —
  `knowledge.search` (low), `usage.get_summary` (low), `document.delete` (critical). LOW/MEDIUM
  tools run synchronously and come back `completed`/`failed` immediately; HIGH/CRITICAL come back
  `pending_approval` with nothing executed yet. Both list endpoints hardcode `limit=50`, no
  pagination. Approve/reject require `tools:approve`, which every user has today — there's only
  one role (`owner`, `["*"]`), a known backend gap, not something this phase changes.
- **Agents** (`POST /agents/run`, `GET /agents`, `GET /agents/{id}/status`): `POST /agents/run`
  runs the entire planner/executor loop **synchronously inside the request** (up to
  `agent_max_execution_seconds`, default 120s) — there is nothing to poll, the response is already
  the final state. **Approving a paused tool call does not resume the run** — confirmed in code and
  `phase4.md`, no `/agents/{id}/resume` route exists. The run stays at `waiting_approval`
  permanently; further progress requires a brand-new `POST /agents/run`.
- **Not implemented anywhere**: no `GET /usage` REST endpoint (only reachable by executing the
  `usage.get_summary` tool), no `/auth/me`, no account/profile-update endpoint.

## What was built

1. **Knowledge** (`/knowledge`) — document list, upload (reusing Phase 2's `uploadDocument`),
   delete with confirmation, and a real `POST /knowledge/search` box.
2. **Tools** (`/tools`) — the 3 real tools, each with a **hand-written** invocation form (not a
   generic JSON-Schema form renderer — 3 small, simple schemas don't justify that complexity), and
   an execution history with real Approve/Reject on `pending_approval` rows.
3. **Agents** (`/agents`) — a goal input (`POST /agents/run`, with an honest "this can take up to
   two minutes" state since the request really blocks that long), a past-runs list, and a detail
   dialog rendering the real step trace (`tool_call` → `observation` → `final_response`). A
   `waiting_approval` run shows the pending tool call inline with Approve/Reject **and an explicit
   note that this will not continue the run** — reusing the same Tools approve/reject functions
   directly, no navigation required.
4. **Settings** — Usage tab now calls `executeTool("usage.get_summary", {days: 30})` and renders
   real request/token counts; Account tab shows real `user`/`tenant` data from `useAuthStore`,
   read-only (no profile-update endpoint exists to back an edit form). The other 7 tabs are
   unchanged — genuinely nothing backs them server-side.

## Design decisions

- **No generic schema-driven form builder.** 3 tools, 3 tiny hand-written forms — a real form
  builder would be more code for a payoff that isn't there yet at this tool count.
- **No polling anywhere in Tools or Agents.** Every write endpoint here (`execute`, `approve`,
  `reject`, `run`) is synchronous — the HTTP response is already the final state.
- **`waiting_approval` is UI'd as a dead end you route around, not a pause you resume** — directly
  matching the backend's own documented design rather than implying a continuation that doesn't
  exist.
- **Account tab stays read-only** — there's no backend endpoint to edit anything, so the tab
  doesn't pretend there is.
- **`/files` (a separate placeholder from `/knowledge`, both in the sidebar per the original
  design)** was left untouched — it wasn't in this phase's scope, and its "wired to real data in
  Phase 3" label was corrected to a phase-agnostic note since Phase 3 completes without it.

## Verified live (2026-08-30)

Full Playwright walkthrough against the live Docker backend: register → upload a real document →
real hybrid search returns a real scored chunk → Tools page lists all 3 real tools with correct
risk badges → ran `usage.get_summary` (low risk, completed synchronously with real numbers) → ran
`document.delete` (critical) against the uploaded document, confirmed it landed `pending_approval`
with the document still genuinely present → approved it from the execution history → confirmed it
then showed `completed` **and the document was actually gone** from the Knowledge page → ran a real
agent goal, waited for the synchronous loop, confirmed the step trace and final response rendered
correctly in the detail dialog and the run appeared in the past-runs list → Settings' Usage tab
showed real numbers, Account tab showed the real logged-in user/tenant. Zero console/page errors.

One real bug the test script itself had (not the app): `page.click('button:has-text("Search")')`
used Playwright's legacy non-strict `page.click()` API, which silently clicked the top bar's
"Search ⌘K" command-menu trigger instead of the Knowledge page's own search submit button, since
both match that text and the legacy API doesn't enforce uniqueness the way `locator().click()`
does. Same class of mistake as a Phase 1 verification bug — fixed by scoping the locator to the
specific form.

## What's deliberately deferred

- A requester/approver separation for tool approvals — no second role exists server-side yet.
- Resuming a `waiting_approval` agent run — no backend mechanism exists.
- Editing anything on the Account tab, or any of the other 7 settings tabs — no backend support.
- `/files` as a real page — out of this phase's scope; conceptually the same data as `/knowledge`
  today, so may end up folded into it rather than built separately.

See [`roadmap.md`](roadmap.md) for how this fits alongside the backend's own phases.
