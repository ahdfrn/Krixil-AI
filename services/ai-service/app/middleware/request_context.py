import time
import uuid
from collections.abc import MutableMapping
from typing import Any

import structlog
from starlette.types import ASGIApp, Receive, Scope, Send

from app.core.logging import get_logger

logger = get_logger("request")


class RequestContextMiddleware:
    """Assigns a request_id (or reuses an inbound X-Request-ID), binds it into structlog's
    contextvars so every log line emitted while handling this request carries it, and logs one
    structured line per request with method/path/status/latency.

    Plain ASGI middleware, not `starlette.middleware.base.BaseHTTPMiddleware`. BaseHTTPMiddleware
    runs the downstream app in a separate task (via an internal anyio task group bridging a
    memory stream) instead of directly in the request's own task — one more layer than necessary,
    and a documented source of subtle ordering/cancellation surprises in Starlette. Investigated
    as a candidate cause of a real, live-caught bug (`POST /agents/run` immediately followed by
    `GET /agents/{id}/status` 404ing) — turned out NOT to be the cause (see the explicit
    `await session.commit()` in `app/agents/router.py`'s `run` endpoint for the actual fix and
    root cause: FastAPI runs `Depends(..., yield ...)` cleanup, e.g. `get_session()`'s own commit,
    *after* the response has already been sent — documented FastAPI behavior, not a bug in it).
    Kept anyway as a real, independent simplification.
    """

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        request_id = str(uuid.uuid4())
        for key, value in scope.get("headers", []):
            if key == b"x-request-id":
                request_id = value.decode("latin-1")
                break
        scope["state"] = {**scope.get("state", {}), "request_id": request_id}

        structlog.contextvars.clear_contextvars()
        structlog.contextvars.bind_contextvars(request_id=request_id)

        start = time.perf_counter()
        status_code = 500

        async def send_wrapper(message: MutableMapping[str, Any]) -> None:
            nonlocal status_code
            if message["type"] == "http.response.start":
                status_code = message["status"]
                headers = list(message.get("headers", []))
                headers.append((b"x-request-id", request_id.encode("latin-1")))
                message = {**message, "headers": headers}
            await send(message)

        method = scope.get("method", "")
        path = scope.get("path", "")
        try:
            await self.app(scope, receive, send_wrapper)
        finally:
            duration_ms = round((time.perf_counter() - start) * 1000, 2)
            logger.info(
                "request_completed",
                method=method,
                path=path,
                status_code=status_code,
                duration_ms=duration_ms,
            )
