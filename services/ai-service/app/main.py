from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from prometheus_fastapi_instrumentator import Instrumentator

from app import evaluation as _evaluation  # noqa: F401  # side-effect import: registers eval cases
from app import tools as _tools  # noqa: F401  # side-effect import: registers every tool
from app.agents.router import router as agents_router
from app.ai.models_router import router as models_router
from app.ai.router import aclose_providers
from app.auth.router import router as auth_router
from app.brain.router import router as brain_router
from app.chat.router import router as chat_router
from app.core.config import get_settings
from app.core.logging import configure_logging, get_logger
from app.finetune.router import router as finetune_router
from app.health.router import router as health_router
from app.mcp.router import router as mcp_router
from app.memory.router import router as memory_router
from app.middleware.request_context import RequestContextMiddleware
from app.observability.tracing import configure_tracing
from app.rag.router import router as rag_router
from app.storage.dependency import get_storage
from app.tools.router import router as tools_router
from app.workspace.host_router import router as host_workspace_router
from app.workspace.router import router as workspace_router

settings = get_settings()
configure_logging()
logger = get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("app_startup", app_env=settings.app_env, model_provider=settings.model_provider)
    await get_storage().ensure_bucket()
    yield
    await aclose_providers()
    logger.info("app_shutdown")


app = FastAPI(title=settings.app_name, version="0.1.0", lifespan=lifespan)

app.add_middleware(RequestContextMiddleware)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(health_router, prefix=settings.api_v1_prefix)
app.include_router(auth_router, prefix=settings.api_v1_prefix)
app.include_router(brain_router, prefix=settings.api_v1_prefix)
app.include_router(mcp_router, prefix=settings.api_v1_prefix)
app.include_router(chat_router, prefix=settings.api_v1_prefix)
app.include_router(rag_router, prefix=settings.api_v1_prefix)
app.include_router(tools_router, prefix=settings.api_v1_prefix)
app.include_router(agents_router, prefix=settings.api_v1_prefix)
app.include_router(models_router, prefix=settings.api_v1_prefix)
app.include_router(memory_router, prefix=settings.api_v1_prefix)
app.include_router(finetune_router, prefix=settings.api_v1_prefix)
app.include_router(workspace_router, prefix=settings.api_v1_prefix)
app.include_router(host_workspace_router, prefix=settings.api_v1_prefix)

# /metrics (Prometheus scrape target) — excluded from its own request metrics.
Instrumentator().instrument(app).expose(app, endpoint="/metrics", include_in_schema=False)
configure_tracing(app, settings)
