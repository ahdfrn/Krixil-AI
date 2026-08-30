# Web app — Phase 5 (production hardening)

## Scope

The roadmap described this as "monitoring, security, multi-tenant UI concerns, scaling." Rather
than treat that as a checklist to pad, I audited the actual current state first (dependency audit,
CI coverage, error handling, behavior across a logout/re-login boundary) and found four concrete,
verifiable things — not a vague hardening pass. "Scaling" has no concrete action without real
deployment infrastructure, which doesn't exist yet (the same gap the backend's own Phase 5 already
documented) — not addressed here, consistent with not fabricating work.

## What was found and fixed

1. **`.github/workflows/ci.yml` covered only `services/ai-service`** — zero automated lint/build
   coverage for `apps/web`. Every frontend phase up to now was verified manually. Added
   `lint-frontend`, `build-frontend`, `security-frontend` jobs mirroring the backend jobs' naming
   and style, independent triggers, no shared `needs`. `next build` already runs TypeScript as part
   of the build, so no separate typecheck job — matches how this project has verified the frontend
   locally since Web Phase 1.

2. **A real cross-tenant UI data-leak window on logout → re-login in the same browser tab.**
   `useAuthStore.logout()` only ever cleared `{user, tenant, accessToken}` — it never touched
   `useChatStore`'s `conversations`/`messagesByConversation`, which are in-memory, page-lifetime
   state with no page reload on sign-out (`router.push` is a client-side nav). If a different
   tenant logged in on the same tab before the next `loadConversations()` fetch resolved, the
   previous tenant's conversation list was briefly still in the store. The sidebar itself was
   already safe (gated behind `isLoadingConversations`), but `command-menu.tsx` reads
   `conversations` with **no loading gate at all** — Ctrl/Cmd+K during that window would show the
   previous tenant's real conversation titles by name. The backend itself was never at risk (the
   tightened `get_conversation_or_404` from the earlier addendum would 404 an actual navigation
   attempt) — this was purely a client-side state-hygiene bug. Fixed with a new
   `chat-store.ts#resetChatState()`, called from `dashboard-shell.tsx`'s existing effect at the
   moment it detects `!isAuthenticated` — the one place that already reacts to every auth
   transition (manual sign-out and a silent 401-triggered logout both converge there).

3. **No error boundary anywhere.** Added `src/app/error.tsx` (branded fallback, "Try again" +
   "Back to chat", reusing the icon-in-rounded-square visual language from `coming-soon.tsx`) and
   `src/app/global-error.tsx` (the one case `error.tsx` can't catch — an error in the root layout
   itself, which needs its own `<html>`/`<body>` and can't depend on `ThemeProvider` or Tailwind
   tokens, since the layout providing those may be what's broken — plain inline styles instead).

4. **Conservative security headers** added via `next.config.ts`'s `headers()`:
   `X-Content-Type-Options: nosniff`, `X-Frame-Options: DENY`, `Referrer-Policy:
   strict-origin-when-cross-origin`. **Deliberately no Content-Security-Policy** — getting one
   right needs testing against a real deployed environment (easy to silently break Radix UI
   portals or Tailwind's runtime styles), and there's no deploy target yet to validate one against.

`npm audit` was already clean (0 vulnerabilities) — now tracked in CI so a future regression gets
caught, mirroring how `pip-audit`/`bandit` already guard the backend.

## Verified live (2026-08-30)

`npm ci` (not just `npm install`) confirmed clean, then the exact CI command sequence run locally
(`npm run lint`, `npm run build` with the same env var CI uses, `npm audit --omit=dev`) — all pass.
Live: registered tenant A, sent a message, signed out, immediately registered tenant B in the same
browser context, and opened the command menu the instant `/chat` loaded (the worst-case timing for
the leak this phase fixed) — confirmed tenant A's conversation title was not shown, and the sidebar
showed a loading state then "No conversations yet" rather than any stale data. Verified the error
boundary with a real uncaught render error (a temporary throwaway test route, deleted after use,
same pattern as this project's verification scripts) — confirmed the branded fallback rendered with
a working "Try again," and that it's visibly distinct from Next.js's own 404 page. Confirmed all
three security headers present on a real page response via `curl -I`. Zero console/page errors
outside of the deliberately-triggered test error (which correctly showed up in the console exactly
because the boundary caught and logged it — that's the boundary working, not a bug).

**Not independently confirmed**: an actual GitHub Actions run of the new CI jobs (no push was made
in this session) — confidence comes from running the identical command sequence locally with a
`npm ci`-clean install, which is the same thing the workflow does on `ubuntu-latest`, but the jobs
haven't been observed going green on GitHub itself yet.

## What's deliberately deferred

- Content-Security-Policy — needs a real deployed environment to validate against.
- Any actual "scaling" work — no deployment target exists yet on either side.
- Monitoring/observability on the frontend (the backend already has Prometheus/Grafana/Jaeger, but
  nothing analogous exists client-side, e.g. a real-user-monitoring or error-tracking service) —
  would mean adding a third-party service and consuming its API key, a product/cost decision, not
  something to default into silently.

See [`roadmap.md`](roadmap.md) for how this fits alongside the backend's own phases.
