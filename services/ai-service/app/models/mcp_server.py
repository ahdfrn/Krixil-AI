import uuid

from sqlalchemy import JSON, ForeignKey, Index, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin, UUIDPKMixin
from app.db.types import GUID


class MCPServer(UUIDPKMixin, TimestampMixin, Base):
    """A real, tenant-configured MCP (Model Context Protocol) server — PRD §10's MCP Hub. Three
    real transports: `stdio` (`command`/`args` spawn a real local subprocess, e.g. `npx -y
    @modelcontextprotocol/server-filesystem /some/real/path`, the same way any other real MCP
    client connects to one), `sse`, and `http` (`url`/`headers` reach a real remote MCP server
    over HTTP). `command`/`args`/`env` are only meaningful for `stdio`; `url`/`headers` only for
    `sse`/`http` — enforced in app/schemas/mcp.py, not here. No servers exist until a tenant adds
    one — nothing is pre-configured or fabricated. See app/mcp/client.py."""

    __tablename__ = "mcp_servers"
    __table_args__ = (
        Index("ix_mcp_servers_tenant_id_id", "tenant_id", "id"),
        UniqueConstraint("tenant_id", "name", name="uq_mcp_servers_tenant_id_name"),
    )

    tenant_id: Mapped[uuid.UUID] = mapped_column(
        GUID(), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False
    )
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    transport: Mapped[str] = mapped_column(String(20), nullable=False, default="stdio")
    command: Mapped[str | None] = mapped_column(String(500), nullable=True)
    args: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    env: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    url: Mapped[str | None] = mapped_column(String(2000), nullable=True)
    headers: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
