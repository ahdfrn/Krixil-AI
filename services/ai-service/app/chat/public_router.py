"""Explicit one-shot public prompts. No project context, history, tools, or fallback."""

from typing import Literal

import httpx
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict, Field

from app.ai.base import ModelMessage
from app.ai.router import ModelRouter
from app.core.rate_limit import enforce_chat_rate_limit
from app.observability.metrics import TOKEN_USAGE
from app.tenancy.context import TenantContext
from app.tenancy.dependencies import get_tenant_context

PUBLIC_MODEL = "nvidia/nemotron-3-ultra-550b-a55b:free"
router = APIRouter(tags=["chat"])


class PublicChatRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    message: str = Field(min_length=1, max_length=4000)
    # Required acknowledgement on EVERY request, not a persistent session permission.
    public_data_consent: Literal[True]


class PublicChatResponse(BaseModel):
    content: str
    model: str
    provider: str = "openrouter"


@router.post(
    "/chat/public",
    response_model=PublicChatResponse,
    dependencies=[Depends(enforce_chat_rate_limit)],
)
async def public_chat(
    payload: PublicChatRequest,
    tenant_ctx: TenantContext = Depends(get_tenant_context),
) -> PublicChatResponse:
    try:
        provider = ModelRouter()._get_named_provider("openrouter")
    except ValueError:
        raise HTTPException(503, "OpenRouter is not configured.") from None
    try:
        result = await provider.generate(
            [
                ModelMessage(
                    "system",
                    "Answer the provided public question in the user's language. "
                    "You have no tools, files, personal memories, or conversation history.",
                ),
                ModelMessage("user", payload.message),
            ],
            model=PUBLIC_MODEL,
            max_tokens=2048,
        )
    except httpx.HTTPStatusError as error:
        code = 429 if error.response.status_code == 429 else 503
        raise HTTPException(code, "Public model unavailable. No other model was called.") from None
    except httpx.RequestError:
        raise HTTPException(503, "Public model connection failed. No fallback was used.") from None
    if not result.content.strip():
        raise HTTPException(502, "Public model returned no answer.")
    for kind in ("prompt", "completion"):
        TOKEN_USAGE.labels(model=result.model, token_type=kind).inc(
            result.usage.get(f"{kind}_tokens", 0)
        )
    return PublicChatResponse(content=result.content, model=result.model)
