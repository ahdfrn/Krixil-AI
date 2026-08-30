# Phase 3 — Tool System & permissions

## Why only 3 tools, not the spec's POS examples

The spec's illustrative tool names (`sales.get_summary`, `inventory.get_low_stock`, ...) belong to
an external POS/inventory system Krixil doesn't have anything to connect to yet — building them
now would mean fabricating data, which proves nothing real and can't be verified against an actual
system. Instead, Phase 3 builds the **Tool System infrastructure completely**, proven with 3 tools
that operate on data Krixil genuinely has: `knowledge.search` (wraps Phase 2's hybrid search),
`usage.get_summary` (aggregates `usage_records`), and `document.delete` (wraps Phase 2's document
deletion). Business/POS tools are a drop-in addition once there's a real system to call — the
registry, permission check, risk gate, and approval workflow don't change for them.

## Execution flow

```
AI/caller requests a tool
 → 404 if unregistered
 → permission check (tenant_ctx.has_permission(tool.required_permission))
 → schema validation (tool.input_model, pydantic)
 → risk check: LOW/MEDIUM run immediately; HIGH/CRITICAL create a "pending_approval"
   ToolExecution row and stop — nothing executes until a human approves
 → execute (wrapped in asyncio.wait_for(tool.timeout_seconds))
 → audit log (tool.approval_requested / tool.completed / tool.failed / tool.rejected)
```

`document.delete` is CRITICAL (matches the spec's own "Delete data → CRITICAL" example exactly),
which is what makes it the right tool to prove the approval workflow with — verified live: request
returns `pending_approval` and the document is confirmed still present; only after
`POST /tools/executions/{id}/approve` does it actually disappear (from both Postgres and MinIO)
and the execution flip to `completed`.

## Permissions

`TenantContext` now carries `permissions: list[str]` (loaded from the user's `Role` on every
request, same place `role` name was already being loaded) plus a `has_permission()` helper
(`"*"` or an exact match). Approving/rejecting a pending execution requires its own
`tools:approve` permission — separate from whatever permission the tool itself requires.

**Documented limitation, not hidden**: the only role that exists right now is `owner` with `["*"]`
permissions, so the same user can currently request *and* approve their own CRITICAL tool call —
there's no requester/approver separation (maker-checker) yet. The gate is real and enforced (the
403 test proves permission-less users are blocked), but segregation of duties needs a second role
and an explicit "can't approve your own request" check, which is a natural, self-contained
follow-up once there's more than one role in practice.

## What's deliberately not built yet

- Per-tool rate limiting (the existing per-tenant chat rate limiter is a reasonable backstop for
  now; a dedicated one is a small addition later if a specific tool needs it)
- A raw/generic database query tool (spec section 11) — semantic tools remain the sanctioned
  path; a governed SQL tool is a bigger, separate piece of work with its own review
- Requester ≠ approver enforcement (see above)

## Verified

Offline suite: 61/61 tests pass — this phase has no Postgres-only pieces (JSON columns, no
pgvector), so unlike Phase 2 it's fully covered offline, including the whole approve/reject
lifecycle and tenant isolation of executions. Also verified live in Docker: migration applied
cleanly, `GET /tools` lists all 3 with correct JSON schemas, requesting `document.delete` parked
it as `pending_approval` without touching the document, approving it deleted the document for
real and flipped the execution to `completed`, and `audit_logs` shows the expected
`tool.approval_requested` → `tool.completed` sequence.
