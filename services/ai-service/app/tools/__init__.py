"""Import every tool module so each one registers itself (via register_tool) on app startup —
same pattern as app/models/__init__.py for SQLAlchemy models."""

from app.tools import document_tools, knowledge_tools, usage_tools  # noqa: F401
