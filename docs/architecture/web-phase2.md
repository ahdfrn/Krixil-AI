# Web app — Phase 2 (auth, real chat/streaming, file upload)

## Scope

Wires `apps/web`'s existing `lib/api/*.ts` seam (built in Phase 1 specifically for this) to the
real `services/ai-service` backend for the three things this phase was scoped to: **auth,
conversation/streaming chat, file upload**. No component was redesigned — only the API layer and
the stores/pages that call it changed, exactly as the Phase 1 seam was meant to allow.

## Request flow

```
Component (login form / composer / etc.)
 ↓
Zustand store action (useAuthStore.setSession / useChatStore.sendMessage / ...)
 ↓
lib/api/*.ts        — real fetch against NEXT_PUBLIC_API_BASE_URL, bearer token attached
 ↓
services/ai-service  — FastAPI, JWT-verified, tenant-scoped
 ↓
store.set(...)        — component re-renders from store state, same as Phase 1
```

## Why the real backend is narrower than the Phase 1 mock implied

Read the actual route/schema source rather than assuming the master spec's aspirational shape.
Real, verified contract:

- **Auth**: Bearer-header JWT only. No cookies, no refresh token, no logout endpoint, no `/me`.
  Token expires in 60 minutes with no way to renew it — a session just goes stale and the user has
  to log back in. Login requires the tenant **slug** (returned at registration), not an email
  lookup — there's no "find my workspace" endpoint.
- **Chat streaming** (`POST /chat/stream`, real SSE): event order is `conversation` (carries the
  new conversation's real id, sent first) → `citations` (only if RAG found any) → `chunk` (repeated
  token deltas) → `done` → `error`. **No tool-call/progress event exists** — RAG search happens
  synchronously server-side before the first event ships.
- **Conversations**: `GET /conversations` / `GET /conversations/{id}` only. No `updated_at`, no
  `model`, no `pinned`/`archived`, and no rename/delete/pin/archive routes at all. Old messages
  carry no citations — those only exist live, in the SSE stream, for that turn.
- **Documents**: `pdf/docx/txt/csv` only (not `xlsx`/images). Ingestion is synchronous — the upload
  response already carries the final `ready`/`failed` status; there's no polling endpoint because
  there's no async job to poll.

Building against a wider surface than this — fake tool-call progress steps, a working
rename/pin/archive/delete, xlsx/image upload — would mean shipping UI that silently does nothing
or crashes against the real API. Every one of these gaps is called out explicitly below instead.

## Key design decisions

- **Token storage: `localStorage` via `useAuthStore` (Zustand + `persist`).** The backend has no
  cookie/refresh mechanism, so there's no way to use an httpOnly cookie without adding a Next.js
  BFF proxy the spec never asked for. Trade-off, stated plainly: a JWT in `localStorage` is
  readable by any injected script — the standard accepted risk for a Bearer-token SPA without a
  BFF. Revisit only if the backend grows cookie/refresh support.
- **New conversations get their id from the first SSE event, not a fabricated client-side one.**
  There's no "create empty conversation" endpoint — a client-invented id passed as
  `conversation_id` would 404. `chat-store.ts`'s `sendMessage` opens the stream with
  `conversation_id` omitted and resolves its returned promise as soon as the `conversation` event
  arrives (not when the stream finishes); the rest of the response keeps streaming into the store
  in the background. `ChatHomePage` awaits that promise, then navigates — so there's a brief pause
  between hitting Send and the URL changing (RAG search + first-byte latency happens before the id
  is even known), unlike Phase 1's instant-navigate-then-stream. Honest to how the backend actually
  behaves, and avoids duplicating message-list rendering across two pages just to hide that pause.
- **`tool-call-display.tsx` is never populated for real chat responses.** There's no backend event
  for it — faking one would be exactly the kind of fabricated status this project's rules reject.
  "Krixil is thinking..." (pre-first-token) stays, since that's honestly true. Real `citations`
  still render, minus the `snippet` field the backend doesn't return (`citation-list.tsx` shows the
  source badge without a tooltip when there's no snippet, instead of an empty one).
- **File attach uploads straight to the tenant's knowledge base, not "to this message."** There's
  no per-message attachment reference in `ChatRequest` — an uploaded file becomes tenant-wide
  RAG-searchable content immediately, same as a Knowledge-base upload. The composer's toast says
  "added to your knowledge base" rather than implying per-message scoping.
- **Rename/pin/archive/delete stay exactly as decided**: visible menu items in `chat-header.tsx`
  and `chat-history-item.tsx`, wired to a "not available yet" toast — the same pattern this
  codebase already used for Tools/Voice-input in Phase 1. The store actions themselves were
  removed (not left as unreachable dead code) since nothing calls them anymore. No backend changes
  in this phase.
- **Model selector stays cosmetic.** No backend endpoint lists models and `ChatRequest` has no
  model field — unchanged from Phase 1, where selecting a model never affected the response either.

## A real bug the live verification caught

`Conversation.title` on the backend (`app/models/conversation.py`) defaults to the literal string
`"New conversation"` and is never derived from the first message anywhere server-side — and with
no rename endpoint, there's no way to fix it after the fact. The first version of this phase's
`chat-store.ts` locally faked a nicer title from the message content on send, which looked correct
for that session but silently reverted to "New conversation" on the next reload/re-login — a
confusing flip-flop only visible by actually refreshing the page after sending, not from reading
the diff. Fixed by not deriving a local title at all; the sidebar now always shows exactly what the
backend actually stores, so there's nothing to revert.

## Verified live (2026-08-30)

Same discipline as Phase 1: no pytest-equivalent exists for this UI, so it was verified by running
both halves together — `docker compose up` for the backend, `npm run dev` for the frontend — and
driving a headless Chromium through register → redirected to `/chat` → send with no prior
conversation → URL updates to `/chat/{realId}` once the id arrives, response streams and renders →
upload a `.txt` file, confirm `ready` status and a citation on a follow-up question → refresh,
confirm the session persists and the conversation reloads from the real `GET /conversations/{id}`
→ sign out → confirm `/login` redirect, including hitting `/chat` directly while logged out → log
back in with the same tenant slug, confirm the conversation list reloads for real.

## What's deliberately deferred

- Rename/delete/pin/archive conversations — no backend endpoints exist; would need new routes
  (rename/delete) and a schema migration (pin/archive) that are out of this phase's scope.
- Model selection actually affecting which model answers — no backend endpoint or request field
  exists for it.
- Any session-refresh/renewal story — the backend issues a flat 60-minute token with no refresh
  path; a stale session just requires logging back in.
- `/knowledge`, `/agents`, `/tools`, `/settings`' non-Appearance tabs — still Web Phase 3.

See [`roadmap.md`](roadmap.md) for how this fits alongside the backend's own phases.
