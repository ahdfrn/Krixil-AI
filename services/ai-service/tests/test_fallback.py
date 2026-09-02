from unittest.mock import AsyncMock

import httpx
import pytest

from app.ai.base import ModelMessage, ModelResponse, ToolCallRequest
from app.ai.fallback import FallbackProvider, ProvidersUnavailable
from app.ai.mock_provider import MockProvider
from app.ai.router import ModelRouter
from app.core.config import Settings
from tests.helpers import auth_headers, register


def provider(name, result=None):
    item = MockProvider()
    item.name = name
    item.generate = AsyncMock(return_value=result or ModelResponse("ok", name))
    item.tool_call = AsyncMock(return_value=result or ModelResponse("ok", name))
    item.embeddings = AsyncMock(return_value=[[1.0]])
    return item


def failure(status=429, headers=None):
    response = httpx.Response(
        status, request=httpx.Request("POST", "https://example.test"), headers=headers
    )
    return httpx.HTTPStatusError("upstream error", request=response.request, response=response)


def test_router_builds_ordered_shared_chain(monkeypatch):
    settings = Settings(model_provider="groq", model_fallback_providers="openrouter,ollama,groq")
    providers = {name: provider(name) for name in ("groq", "openrouter", "ollama")}
    monkeypatch.setattr("app.ai.router.get_settings", lambda: settings)
    monkeypatch.setattr(ModelRouter, "_get_named_provider", lambda self, name: providers[name])
    monkeypatch.setattr("app.ai.router._fallback_instances", {})
    result = ModelRouter().get_provider()
    assert [item.name for item in result.providers] == ["groq", "openrouter", "ollama"]
    assert ModelRouter().get_provider() is result


def test_router_no_chain_without_explicit_consent(monkeypatch):
    primary = provider("groq")
    monkeypatch.setattr(
        "app.ai.router.get_settings",
        lambda: Settings(model_provider="groq", model_fallback_providers=""),
    )
    monkeypatch.setattr(ModelRouter, "_get_named_provider", lambda self, name: primary)
    assert ModelRouter().get_provider() is primary


def test_retry_after_http_date_and_quota_code(monkeypatch):
    monkeypatch.setattr("app.ai.fallback.time.time", lambda: 0)
    chain = FallbackProvider([provider("one")])
    assert chain._delay(failure(headers={"Retry-After": "Thu, 01 Jan 1970 00:02:00 GMT"})) == 120
    response = httpx.Response(
        429,
        request=httpx.Request("POST", "https://example.test"),
        json={"error": {"code": "insufficient_quota"}},
    )
    error = httpx.HTTPStatusError("quota", request=response.request, response=response)
    assert chain._delay(error) == 3600


async def test_three_providers_continue_with_identical_tool_history():
    first, second, third = (provider(name) for name in ("one", "two", "three"))
    first.tool_call.side_effect = failure(429)
    second.tool_call.side_effect = failure(402)
    third.tool_call.return_value = ModelResponse(
        "", "third-model", tool_calls=[ToolCallRequest("host.read_file", {"path": "README.md"})]
    )
    chain = FallbackProvider([first, second, third])
    messages = [
        ModelMessage("user", "Fix it"),
        ModelMessage("user", 'Tool result: {"already_written": true}'),
    ]
    tools = []
    response = await chain.tool_call(messages, tools, model="primary-model")
    assert response.model == "third-model"
    first.tool_call.assert_awaited_once_with(messages, tools, model="primary-model")
    second.tool_call.assert_awaited_once_with(messages, tools)
    third.tool_call.assert_awaited_once_with(messages, tools)
    await chain.tool_call(messages, tools, model="primary-model")
    assert first.tool_call.await_count == second.tool_call.await_count == 1
    assert third.tool_call.await_count == 2


async def test_agent_keeps_run_and_completed_tool_when_provider_changes(client, monkeypatch):
    first, second = provider("one"), provider("two")
    first.tool_call.side_effect = [
        ModelResponse("", "first-model", tool_calls=[ToolCallRequest("usage.get_summary", {})]),
        failure(429),
    ]
    second.tool_call.return_value = ModelResponse("Task complete", "backup-model")
    chain = FallbackProvider([first, second])
    monkeypatch.setattr("app.agents.router.model_router.get_provider", lambda: chain)
    registered = await register(client)
    headers = auth_headers(registered["access_token"])
    started = await client.post("/api/v1/agents/run", json={"goal": "Check usage"}, headers=headers)
    assert started.status_code == 200
    run_id = started.json()["id"]
    response = await client.get(f"/api/v1/agents/{run_id}/status", headers=headers)
    body = response.json()
    assert body["status"] == "completed"
    assert body["tool_call_count"] == 1
    assert body["final_response"] == "Task complete"
    assert len([step for step in body["steps"] if step["type"] == "tool_call"]) == 1
    assert body["steps"][-1]["content"]["provider"] == "two"
    messages = second.tool_call.call_args.args[0]
    assert any("Tool result:" in message.content for message in messages)


@pytest.mark.parametrize("status", [402, 429, 500, 502, 503, 504])
async def test_transient_errors_fall_back(status):
    first, second = provider("one"), provider("two")
    first.generate.side_effect = failure(status)
    result = await FallbackProvider([first, second]).generate([])
    assert result.model == "two"


@pytest.mark.parametrize("status", [400, 401, 403, 404, 422])
async def test_configuration_and_context_errors_are_not_masked(status):
    first, second = provider("one"), provider("two")
    first.generate.side_effect = failure(status)
    with pytest.raises(httpx.HTTPStatusError):
        await FallbackProvider([first, second]).generate([])
    second.generate.assert_not_awaited()


async def test_retry_after_and_recovery(monkeypatch):
    clock = [100.0]
    monkeypatch.setattr("app.ai.fallback.time.monotonic", lambda: clock[0])
    first, second = provider("one"), provider("two")
    first.generate.side_effect = failure(headers={"Retry-After": "120"})
    chain = FallbackProvider([first, second])
    await chain.generate([])
    assert chain.unavailable_until[("one", "default")] == 220
    first.generate.side_effect = None
    clock[0] = 219
    assert (await chain.generate([])).model == "two"
    clock[0] = 221
    assert (await chain.generate([])).model == "one"


async def test_all_exhausted_raises_without_busy_loop():
    first, second = provider("one"), provider("two")
    first.generate.side_effect = failure()
    second.generate.side_effect = httpx.ConnectError("offline")
    chain = FallbackProvider([first, second])
    for _ in range(2):
        with pytest.raises(ProvidersUnavailable, match="All configured"):
            await chain.generate([])
    assert first.generate.await_count == second.generate.await_count == 1


async def test_embeddings_do_not_switch_vector_spaces():
    first, second = provider("one"), provider("two")
    first.embeddings.side_effect = failure()
    with pytest.raises(httpx.HTTPStatusError):
        await FallbackProvider([first, second]).embeddings(["document"])
    second.embeddings.assert_not_awaited()


@pytest.mark.parametrize("partial", [False, True])
async def test_stream_switches_only_before_first_content(partial):
    first, second = provider("one"), provider("two")

    async def broken(*args, **kwargs):
        if partial:
            yield "partial"
        raise failure()

    async def healthy(*args, **kwargs):
        yield "complete"

    first.stream, second.stream = broken, healthy
    received = []
    stream = FallbackProvider([first, second]).stream([])
    if partial:
        with pytest.raises(httpx.HTTPStatusError):
            async for chunk in stream:
                received.append(chunk)
        assert received == ["partial"]
    else:
        assert [chunk async for chunk in stream] == ["complete"]
