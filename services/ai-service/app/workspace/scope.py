"""Authenticated host transport headers; never sourced from model arguments."""

from urllib.parse import quote

from app.core.config import get_settings
from app.tenancy.context import TenantContext


def host_headers(tenant_ctx: TenantContext | None = None) -> dict[str, str]:
    headers = {"X-Krixil-Host-Key": get_settings().host_runner_api_key}
    if tenant_ctx and tenant_ctx.workspace_root:
        headers["X-Krixil-Workspace"] = quote(tenant_ctx.workspace_root, safe="")
    return headers
