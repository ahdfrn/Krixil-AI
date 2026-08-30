"""Import every model so Base.metadata is fully populated for Alembic autogenerate and
`Base.metadata.create_all` in tests — SQLAlchemy only registers a model on class definition."""

from app.models.agent_run import AgentRun
from app.models.agent_step import AgentStep
from app.models.audit_log import AuditLog
from app.models.conversation import Conversation
from app.models.document import Document
from app.models.document_chunk import DocumentChunk
from app.models.message import Message
from app.models.role import Role
from app.models.tenant import Tenant
from app.models.tool_execution import ToolExecution
from app.models.usage_record import UsageRecord
from app.models.user import User

__all__ = [
    "AgentRun",
    "AgentStep",
    "AuditLog",
    "Conversation",
    "Document",
    "DocumentChunk",
    "Message",
    "Role",
    "Tenant",
    "ToolExecution",
    "UsageRecord",
    "User",
]
