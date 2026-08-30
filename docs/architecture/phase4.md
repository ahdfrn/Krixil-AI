# Phase 4 — Agents

## Why one generalist agent, not the spec's specialized ones

Same reasoning as Phase 3's tools: the spec's specialized agents (Research, Coding, Business
Analyst, ...) need real capabilities Krixil doesn't have yet — web search, a code sandbox, a real
POS connection. Building them now would be a thin wrapper around nothing. Phase 4 builds the
**agent execution loop completely** — planner/executor/observer, budgets, human-approval
integration — and proves it with one generalist agent that reasons over whatever tools are
actually registered (all 3 from Phase 3 today). A specialized agent later is a different system
prompt and possibly a narrower tool list; the loop underneath doesn't change.

## The loop

```
goal
 → provider.tool_call(messages, tools)     ("UNDERSTAND" + "PLAN" + "SELECT TOOLS", one call)
 → no tool_calls in response?  → final answer, done
 → tool_calls[0]                            (only the first — see below)
 → tool_call_count budget check
 → app.tools.service.request_tool_execution() — same Phase 3 path everything else uses, so
   permission checks, risk-based approval, schema validation, and audit logging all apply
   identically to an agent-initiated call as to a direct API call
 → pending_approval? → stop, status="waiting_approval", record which execution is pending
 → otherwise: observation appended to the conversation, loop
 → step/time budget exceeded at any point → stop, status="stopped", reason recorded
```

Runs synchronously inside `POST /agents/run` — same trade-off as Phase 2's document ingestion,
no background job queue yet. Only the *first* tool call per model response is executed, even if a
real model returned several — keeps the step/observation bookkeeping one-to-one and simple;
worth revisiting if a real model's parallel-tool-call habit turns out to matter in practice.

## `tool_call()` is now real

Deferred since Phase 1 with an explicit "lands with the Tool System phase" — that phase has now
happened twice over (Phase 3's tools, Phase 4's agent loop), so this was the right moment:

- **`CloudModelProvider`**: sends OpenAI's native `tools=` function-calling format, parses
  `message.tool_calls` back into structured `ToolCallRequest`s. Standard, verified with respx
  against a fabricated structured tool-call response.
- **`MockProvider`**: no real reasoning available, so it uses a keyword heuristic — a tool
  matches if any `\b`-word-boundary-delimited part of its name (split on `.`/`_`, >3 chars)
  appears in the latest user message; required `string` fields get the whole message, required
  `uuid`-format fields get a regex-extracted UUID from it, anything else required is left unset
  (which correctly fails schema validation rather than inventing a value). **A real bug this
  caught during testing**: an early plain-substring version of this matched "document" inside the
  literal string "document_id" — which is exactly what a failed `document.delete` call's own
  Pydantic error message contains — so a validation failure kept re-triggering the same failing
  tool call. The step/tool-call budgets caught it and stopped the run safely either way (which is
  the point of having them), but the word-boundary fix stops the false match at the source. Only
  found by actually running an agent against a scenario designed to fail, not by reading the code.

## Budgets

`max_steps` (default 8), `max_tool_calls` (default 5), `max_execution_seconds` (default 120) —
server-configured only in Phase 4, not per-request; a natural, self-contained addition later if
needed. Exceeding any of them stops the run with `status="stopped"` and a specific
`error_message`, never a crash or a silent hang.

## Human approval: stop, don't auto-resume

A HIGH/CRITICAL tool call inside an agent run goes through the exact same
`pending_approval` → `POST /tools/executions/{id}/approve` flow Phase 3 already has. What Phase 4
deliberately does **not** do is automatically resume the agent run after that approval — the run
stays at `status="waiting_approval"` even once its underlying tool execution is `completed`.
Auto-resume needs to reconstruct conversation state reliably days later and handle a rejected
approval gracefully; half-building that now risks a resume path that silently loses context. The
current, honest pattern: approve via the Phase 3 endpoint (which really executes the tool — this
is verified live below), and start a fresh agent run with the outcome as context if more work is
needed.

## Verified

Offline suite: 74/74 tests pass, including the budget boundaries, the approval pause, the
tenant-isolation of runs, and the mock-heuristic false-positive fix above. Live in Docker:
a no-tool goal completed in one step; a goal matching `usage.get_summary` called it and produced
a final answer built from the real result; a goal to delete a real uploaded document paused at
`waiting_approval` with the document still present; approving that execution via the Phase 3
endpoint deleted it for real; and `GET /agents/{id}/status` showed the exact `tool_call` →
`observation` step trace matching what happened.
