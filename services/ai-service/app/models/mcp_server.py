import uuid

from sqlalchemy import JSON, ForeignKey, Index, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin, UUIDPKMixin
from app.db.types import GUID


class MCPServer(UUIDPKMixin, TimestampMixin, Base):
    """A real, tenant-configured MCP (Model Context Protocol) server — PRD §10's MCP Hub. Stdio
    transport only in this pass: `command`/`args` spawn a real local subprocess (e.g. `npx -y
    @modelcontextprotocol/server-filesystem /some/real/path`), the same way any other real MCP
    client (Claude Desktop, etc.) connects to one. No servers exist until a tenant adds one —
    nothing is pre-configured or fabricated. See app/mcp/client.py."""

    __tablename__ = "mcp_servers"
    __table_args__ = (
        Index("ix_mcp_servers_tenant_id_id", "tenant_id", "id"),
        UniqueConstraint("tenant_id", "name", name="uq_mcp_servers_tenant_id_name"),
    )

    tenant_id: Mapped[uuid.UUID] = mapped_column(
        GUID(), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False
    )
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    command: Mapped[str] = mapped_column(String(500), nullable=False)
    args: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    env: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
