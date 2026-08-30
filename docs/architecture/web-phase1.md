# Web app — Phase 1 (UI, mock data)

> Named `web-phase1` rather than `phase1.md` to avoid colliding with the backend's own Phase 1
> ("Real model providers + memory") — the web app has its own, separate 5-phase plan from its own
> master-prompt spec, unrelated to the backend's phase numbering.

## Scope

`apps/web` — the Krixil AI chat/workspace web app, built strictly to PHASE 1 of its spec: a
complete, premium UI running entirely on mock/in-memory data, with **zero** backend wiring, auth,
or real API calls. The spec's own instruction was explicit: build the UI first, prove it end to
end, and only then replace mock data with real calls — not build frontend and backend
simultaneously.

## Request flow (Phase 1 — all client-side, no network)

```
Component (e.g. ChatComposer)
 ↓
Zustand store action (useChatStore.sendMessage)
 ↓
lib/api/*.ts        — thin async wrapper, awaits an artificial delay
 ↓
lib/mock/*.ts        — static/generated mock data, canned streaming responses
 ↓
store.set(...)        — component re-renders from store state
```

`lib/api/*.ts` is the only layer meant to change in Phase 2: same function signatures, same
return shapes, swapped internals (`fetch("/api/v1/...")` instead of `lib/mock/*`). No component
imports `lib/mock/*` directly — everything goes through `lib/api/*`, so the seam is real, not
aspirational.

## Why mock-data-first (not building against the real backend already sitting at `D:\Krixil`)

The backend (`services/ai-service`) is fully built and could theoretically be wired up now. Two
reasons this Phase 1 didn't do that, matching the spec's own explicit instruction:

1. **The spec sequences it this way on purpose** — UI/UX quality (layout, responsiveness, dark
   mode, component design) is easier to iterate on and get right without also debugging live
   network/auth/streaming issues at the same time.
2. **The backend has no user-facing auth flow session cookie/token issuance wired to a browser
   client yet** (its auth is API-only, exercised via pytest/httpx, not a browser session) — Phase 2
   is exactly the phase that closes that gap on both sides at once.

## Component architecture

`src/app/` (routes) → `src/components/{layout,chat,ui}/` → `src/stores/` (Zustand: `chat-store`,
`ui-store`) → `src/lib/api/` (seam) → `src/lib/mock/` (Phase 1 only) → `src/types/`.

Route groups: `(dashboard)` wraps every real page in `DashboardShell` (sidebar + top bar + main).
`/chat` is the empty-state home; `/chat/[conversationId]` is a live conversation; `/knowledge`,
`/agents`, `/tools`, `/files` are thin "coming soon" placeholders (Phase 3 territory); `/settings`
has a working Appearance tab and 9 placeholder tabs matching the spec's named sections.

State pattern: Zustand store is the source of truth after initial load. `lib/api` is used for the
initial hydration fetch (`loadConversations`, `loadMessages`); further mutations (send/rename/
delete/pin/archive) call store actions directly, which in Phase 2 will call mutating `lib/api`
functions instead of mutating local state directly — same seam, not yet exercised because Phase 1
has no server to mutate.

## Streaming simulation

`lib/mock/responses.ts`'s `streamCannedResponse(content, signal)` is an async generator yielding
word-by-word chunks with randomized delays, honoring an `AbortSignal` — deliberately shaped like
real SSE token consumption so swapping in a real `fetch` + `ReadableStream` reader in Phase 2
changes only the producer, not any consumer code in `chat-store.ts` or the message components.

## Verified live (2026-08-30)

No pytest-equivalent exists for a UI-only app. Verified by starting `npm run dev` and driving a
headless Chromium (Playwright) through: suggestion-card prefill → send → streaming response →
markdown/code/table/citation/tool-call rendering → sidebar collapse/expand → chat-history date
grouping → command menu (Ctrl/Cmd+K) → dark/light theme toggle → mobile drawer → settings page,
checking console/page errors after each step. `npm run lint`, `npm run build`, `npx tsc --noEmit`
all clean.

Four real bugs were caught only by actually running the app (lint/build/typecheck missed all of
them — the same lesson as the backend's live-verification history in `roadmap.md`/`phase5.md`):

1. **Conversation pages redirected to `/chat` on every direct/hard navigation.**
   `ConversationPage`'s guard effect (`if (!isLoadingConversations && !conversation) router.replace
   ("/chat")`) ran before `DashboardShell`'s `loadConversations()` effect had flipped
   `isLoadingConversations` to `true` — React fires child effects before parent effects on mount,
   and the store defaulted that flag to `false`. Fixed by defaulting `isLoadingConversations: true`
   in the store's initial state, so both fields flip together in one `set()` call once loading
   actually finishes.
2. **The sidebar's collapse button was only ~40% clickable.** `SidebarContent`'s root div — the
   lone flex-item child of a row-direction `<aside>` — had no `min-w-0`, so its default
   `min-width: auto` blocked it from shrinking to the aside's fixed 256px width. The whole sidebar
   column silently rendered ~26px too wide (`overflow: visible` is the default — nothing clips it)
   and was painted over by the adjacent `<main>` sibling. One `min-w-0` class fixed every affected
   row, not just the button.
3. **The command menu (Ctrl/Cmd+K) crashed on open**: `TypeError: Cannot read properties of
   undefined (reading 'subscribe')`. The generated `ui/command.tsx`'s `CommandDialog` rendered
   `{children}` directly inside `DialogContent` without wrapping them in the `<Command>` (cmdk
   root) primitive that supplies `CommandInput`/`CommandList`/etc.'s internal store. Looks like an
   incomplete shadcn codegen output for the Radix flavor, not something specific to this project —
   worth checking after any future `shadcn add` here.
4. **Hydration-mismatch warning on `/settings`'s Appearance tab.** The theme-swatch "selected"
   styling read `useTheme()`'s `theme` directly, which is `undefined` during SSR and only resolves
   client-side. Fixed with the standard `mounted`-flag-in-`useEffect` pattern (with a targeted
   `eslint-disable` for `react-hooks/set-state-in-effect` — the recognized correct fix for this
   exact next-themes constraint, not a case that lint rule is meant to catch).

## What's deliberately deferred

- All backend wiring: auth (login/register/session), real `/api/v1/chat` + `/chat/stream` calls,
  real file upload processing. This is Phase 2 of the web app's own spec.
- `/knowledge`, `/agents`, `/tools`, `/settings`' non-Appearance tabs — placeholder pages only,
  real functionality is Phase 3 of the web app's own spec.
- Persisted client state (Zustand has no persistence middleware) — acceptable while everything is
  mock data anyway; revisit once real auth sessions exist.

See [`roadmap.md`](roadmap.md) for how this fits alongside the backend's own phases.
