from fastapi import APIRouter, Depends

from app.ai.catalog import get_model_catalog
from app.schemas.model import ModelOut
from app.tenancy.context import TenantContext
from app.tenancy.dependencies import get_tenant_context

router = APIRouter(tags=["models"])


@router.get("/models", response_model=list[ModelOut])
async def list_models(tenant_ctx: TenantContext = Depends(get_tenant_context)) -> list[ModelOut]:
    return get_model_catalog()
