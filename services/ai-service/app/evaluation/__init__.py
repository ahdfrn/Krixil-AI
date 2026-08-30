"""Import every case module so each one registers itself (via register_case) — same pattern as
app/tools/__init__.py."""

from app.evaluation import latency_cases, rag_cases, tool_cases  # noqa: F401
