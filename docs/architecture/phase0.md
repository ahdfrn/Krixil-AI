# Phase 0 — Foundation architecture

## Scope

One FastAPI service (`services/ai-service`), single process, no RAG/agents/tools/fine-tuning yet.
Goal: a correctly multi-tenant, secure-by-default skeleton that later phases extend rather than rewrite.

## Request flow

```
Client
 ↓
FastAPI app (services/ai-service)
 ├── RequestIdMiddleware        → generates/propagates X-Request-ID
 ├── LoggingMiddleware          → structured JSON log per request (method, path, status, latency, request_id)
 ├── CORS
 ↓
Route handler
 ├── auth: OAuth2 bearer token → decode JWT → load User from DB → verify tenant_id in token matches DB row
 ├── tenancy: derive TenantContext(tenant_id, user_id, role) from the loaded User — never trusted from
 │            the request body/query, only from the verified token + DB row
 ↓
Service layer (e.g. ChatService) — every query is scoped by tenant_id explicitly, never a bare `SELECT *`
 ↓
SQLAlchemy async session → PostgreSQL (tenant_id indexed + FK on every tenant-owned table)
Model Router → ModelProvider (MockProvider in Phase 0)
```

## Why a single service (not the full microservice split yet)

The long-term spec calls for separate api-gateway / auth-service / ai-service / agent-service / memory-service /
rag-service / tool-service / document-service / evaluation-service. Standing all of those up now, before there's
any RAG, tools, or agents to serve, would be pure ceremony — empty services calling each other over HTTP for no
reason. Phase 0 ships one service with internal module boundaries that already match those future seams
(`app/auth`, `app/tenancy`, `app/ai`, `app/chat`, `app/db`, `app/models`), so extracting a real service later is a
move-and-wire-HTTP operation, not a redesign.

## Tenant isolation (defense in depth, started now)

1. **Database layer**: every tenant-owned table has a non-null `tenant_id` FK to `tenants.id` with
   `ON DELETE CASCADE`, plus a composite index `(tenant_id, id)`. Uniqueness constraints (e.g. user email) are
   scoped `(tenant_id, column)`, not global — so tenant A can never collide with or infer tenant B's data via a
   uniqueness error.
2. **Application layer**: `TenantContext` is built once, from the DB-verified `User` row (not from client input),
   and every repository/service method takes it as a required argument — there is no code path that queries
   `conversations`/`messages` without a `tenant_id` filter.
2b. **Token/DB cross-check**: the JWT carries `tenant_id`, but on every request the API also loads the user from
   the DB and rejects the request if the DB's `tenant_id` doesn't match the token's — a stale or tampered token
   can't be used to jump tenants even if the signature were somehow otherwise valid.
3. **Permission layer**: minimal in Phase 0 — a `role` with a `permissions` list exists on every user so RBAC
   checks have somewhere to plug in starting Phase 3 (tools), without a schema change.

## Model abstraction

`ModelProvider` (ABC): `generate`, `stream`, `embeddings`, `tool_call`, `health_check`. `ModelRouter` resolves a
provider from `MODEL_PROVIDER` env var — only `"mock"` is registered in Phase 0, so the app boots and is fully
testable with zero external API keys. Real cloud/self-hosted providers are added in Phase 1 behind the same
interface; no business logic elsewhere references a concrete provider.

## What's deliberately deferred

- RAG, documents, embeddings storage (pgvector extension is enabled in the initial migration so Phase 2 doesn't
  need a schema-migration story change, but no vector columns exist yet)
- Tools, tool permissions, agents, human approval
- Real cloud model provider, rate limiting, evaluation harness, OpenTelemetry/Prometheus/Grafana
- Kubernetes, Terraform, multiple environments

See [`roadmap.md`](roadmap.md) for when each of these lands.
