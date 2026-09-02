"""Import every tool module so each one registers itself (via register_tool) on app startup —
same pattern as app/models/__init__.py for SQLAlchemy models."""

from app.tools import (  # noqa: F401
    brain_tools,
    code_tools,
    document_tools,
    host_tools,
    knowledge_tools,
    mcp_tools,
    usage_tools,
    web_tools,
)
