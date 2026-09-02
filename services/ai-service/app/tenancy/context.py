import uuid
from dataclasses import dataclass


@dataclass(frozen=True)
class TenantContext:
    """Request-scoped identity. Built only from a DB-verified User row (see
    app/auth/dependencies.py) — never from client-supplied body/query/path values."""

    tenant_id: uuid.UUID
    user_id: uuid.UUID
    role: str
    permissions: list[str]
    workspace_root: str | None = None

    def has_permission(self, required: str) -> bool:
        return "*" in self.permissions or required in self.permissions
