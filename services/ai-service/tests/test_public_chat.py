from unittest.mock import AsyncMock, patch

import httpx
import pytest

from app.ai.base import ModelResponse
from app.chat.public_router import PUBLIC_MODEL
from tests.helpers import auth_headers, register


async def test_public_chat_is_one_shot_without_implicit_context(client):
    registered = await register(client)
    provider = AsyncMock()
    provider.generate.return_value = ModelResponse("Public answer", PUBLIC_MODEL)
    with (
        patch("app.chat.public_router.ModelRouter._get_named_provider", return_value=provider),
        patch("app.chat.router.get_context_messages", new_callable=AsyncMock) as history,
        patch("app.chat.router.build_memory_context", new_callable=AsyncMock) as memory,
        patch("app.chat.router.build_rag_context", new_callable=AsyncMock) as rag,
    ):
        response = await client.post(
            "/api/v1/chat/public",
            headers=auth_headers(registered["access_token"]),
            json={"message": "Explain recursion", "public_data_consent": True},
        )
    assert response.status_code == 200
    assert response.json()["content"] == "Public answer"
    messages = provider.generate.call_args.args[0]
    assert len(messages) == 2
    assert messages[1].content == "Explain recursion"
    assert provider.generate.call_args.kwargs == {"model": PUBLIC_MODEL, "max_tokens": 2048}
    provider.tool_call.assert_not_awaited()
    history.assert_not_awaited()
    memory.assert_not_awaited()
    rag.assert_not_awaited()
    conversations = await client.get(
        "/api/v1/conversations", headers=auth_headers(registered["access_token"])
    )
    assert conversations.json() == []


@pytest.mark.parametrize(
    "extra",
    [
        {},
        {"public_data_consent": False},
        {"public_data_consent": True, "conversation_id": "old-context"},
        {"public_data_consent": True, "tools": []},
        {"public_data_consent": True, "model": "another-model"},
    ],
)
async def test_public_chat_rejects_missing_consent_or_implicit_context(client, extra):
    registered = await register(client)
    with patch("app.chat.public_router.ModelRouter._get_named_provider") as factory:
        response = await client.post(
            "/api/v1/chat/public",
            headers=auth_headers(registered["access_token"]),
            json={"message": "hello", **extra},
        )
    assert response.status_code == 422
    factory.assert_not_called()


async def test_public_chat_does_not_fall_back_on_rate_limit(client):
    registered = await register(client)
    provider = AsyncMock()
    request = httpx.Request("POST", "https://example.test")
    provider.generate.side_effect = httpx.HTTPStatusError(
        "private upstream details", request=request, response=httpx.Response(429, request=request)
    )
    with patch(
        "app.chat.public_router.ModelRouter._get_named_provider", return_value=provider
    ) as factory:
        response = await client.post(
            "/api/v1/chat/public",
            headers=auth_headers(registered["access_token"]),
            json={"message": "hello", "public_data_consent": True},
        )
    assert response.status_code == 429
    assert "private upstream" not in response.text
    factory.assert_called_once_with("openrouter")
    assert provider.generate.await_count == 1


async def test_public_chat_requires_authentication(client):
    response = await client.post(
        "/api/v1/chat/public", json={"message": "hello", "public_data_consent": True}
    )
    assert response.status_code == 401
