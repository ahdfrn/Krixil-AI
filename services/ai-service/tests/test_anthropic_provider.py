import json
from collections.abc import AsyncIterator

import httpx
import pytest
import respx

from app.ai.anthropic_provider import AnthropicModelProvider
from app.ai.base import ModelMessage, ModelProvider, ModelResponse, ToolSchema

BASE_URL = "https://mock.anthropic.test/v1"


class _FakeEmbeddingsProvider(ModelProvider):
    """Stands in for the Ollama-backed embeddings delegate (app/ai/router.py) — real behavior
    under test here is "AnthropicModelProvider.embeddings() forwards to whatever it was given",
    not Ollama's own embeddings shape (already covered by test_cloud_provider.py)."""

    name = "fake-embeddings"

    def __init__(self):
        self.calls: list[list[str]] = []

    async def generate(self, messages, **kwargs) -> ModelResponse:  # pragma: no cover - unused
        raise NotImplementedError

    def stream(self, messages, **kwargs) -> AsyncIterator[str]:  # pragma: no cover - unused
        raise NotImplementedError

    async def embeddings(self, texts: list[str]) -> list[list[float]]:
        self.calls.append(texts)
        return [[0.5, 0.5] for _ in texts]

    async def tool_call(self, messages, tools, **kwargs) -> ModelResponse:  # pragma: no cover
        raise NotImplementedError

    async def health_check(self) -> bool:  # pragma: no cover - unused
        return True


@pytest.fixture
async def fake_embeddings():
    return _FakeEmbeddingsProvider()


@pytest.fixture
async def provider(fake_embeddings):
    p = AnthropicModelProvider(
        api_key="test-key",
        base_url=BASE_URL,
        model="claude-sonnet-5",
        api_version="2023-06-01",
        max_tokens=1024,
        embeddings_provider=fake_embeddings,
    )
    yield p
    await p.aclose()


async def test_generate_returns_content_and_usage(provider):
    with respx.mock(assert_all_called=True) as mock:
        route = mock.post(f"{BASE_URL}/messages").mock(
            return_value=httpx.Response(
                200,
                json={
                    "model": "claude-sonnet-5",
                    "content": [{"type": "text", "text": "Hello there"}],
                    "usage": {"input_tokens": 5, "completion_tokens": 3, "output_tokens": 3},
                },
            )
        )
        response = await provider.generate(
            [
                ModelMessage(role="system", content="Be helpful."),
                ModelMessage(role="user", content="hi"),
            ]
        )

    assert response.content == "Hello there"
    assert response.usage == {"prompt_tokens": 5, "completion_tokens": 3}

    sent_body = json.loads(route.calls.last.request.content)
    # The system message must be lifted to the top-level `system` field, not left in `messages`
    # — Anthropic's API rejects role="system" entries inside the array entirely.
    assert sent_body["system"] == "Be helpful."
    assert sent_body["messages"] == [{"role": "user", "content": "hi"}]
    assert sent_body["max_tokens"] == 1024


async def test_generate_raises_on_http_error(provider):
    with respx.mock(assert_all_called=True) as mock:
        mock.post(f"{BASE_URL}/messages").mock(return_value=httpx.Response(401))
        with pytest.raises(httpx.HTTPStatusError):
            await provider.generate([ModelMessage(role="user", content="hi")])


async def test_stream_yields_text_deltas_only(provider):
    sse_body = (
        'data: {"type":"content_block_start","content_block":{"type":"text"}}\n\n'
        'data: {"type":"content_block_delta","delta":{"type":"text_delta","text":"Hello"}}\n\n'
        'data: {"type":"content_block_delta","delta":{"type":"text_delta","text":" world"}}\n\n'
        'data: {"type":"content_block_stop"}\n\n'
        'data: {"type":"message_stop"}\n\n'
    )
    with respx.mock(assert_all_called=True) as mock:
        mock.post(f"{BASE_URL}/messages").mock(
            return_value=httpx.Response(
                200, content=sse_body.encode(), headers={"content-type": "text/event-stream"}
            )
        )
        chunks = [
            delta async for delta in provider.stream([ModelMessage(role="user", content="hi")])
        ]

    assert chunks == ["Hello", " world"]


async def test_embeddings_delegates_to_the_injected_provider(provider, fake_embeddings):
    result = await provider.embeddings(["a", "b"])
    assert result == [[0.5, 0.5], [0.5, 0.5]]
    assert fake_embeddings.calls == [["a", "b"]]


async def test_tool_call_parses_tool_use_blocks(provider):
    tool = ToolSchema(
        name="knowledge.search", description="Search docs", parameters={"type": "object"}
    )

    with respx.mock(assert_all_called=True) as mock:
        route = mock.post(f"{BASE_URL}/messages").mock(
            return_value=httpx.Response(
                200,
                json={
                    "model": "claude-sonnet-5",
                    "content": [
                        {
                            "type": "tool_use",
                            "id": "toolu_1",
                            "name": "knowledge.search",
                            "input": {"query": "pgvector"},
                        }
                    ],
                    "usage": {"input_tokens": 10, "output_tokens": 4},
                },
            )
        )
        response = await provider.tool_call(
            [ModelMessage(role="user", content="search for pgvector")], [tool]
        )

    sent_body = json.loads(route.calls.last.request.content)
    assert sent_body["tools"] == [
        {
            "name": "knowledge.search",
            "description": "Search docs",
            "input_schema": {"type": "object"},
        }
    ]

    assert response.content == ""
    assert len(response.tool_calls) == 1
    assert response.tool_calls[0].name == "knowledge.search"
    assert response.tool_calls[0].arguments == {"query": "pgvector"}


async def test_tool_call_with_only_text_returns_plain_content(provider):
    with respx.mock(assert_all_called=True) as mock:
        mock.post(f"{BASE_URL}/messages").mock(
            return_value=httpx.Response(
                200,
                json={
                    "model": "claude-sonnet-5",
                    "content": [{"type": "text", "text": "just an answer"}],
                    "usage": {"input_tokens": 3, "output_tokens": 2},
                },
            )
        )
        response = await provider.tool_call([ModelMessage(role="user", content="hi")], [])

    assert response.content == "just an answer"
    assert response.tool_calls == []


async def test_requests_use_anthropic_auth_headers_not_bearer(provider):
    with respx.mock(assert_all_called=True) as mock:
        route = mock.post(f"{BASE_URL}/messages").mock(
            return_value=httpx.Response(
                200, json={"model": "claude-sonnet-5", "content": [], "usage": {}}
            )
        )
        await provider.generate([ModelMessage(role="user", content="hi")])

    sent_headers = route.calls.last.request.headers
    assert sent_headers["x-api-key"] == "test-key"
    assert sent_headers["anthropic-version"] == "2023-06-01"
    assert "authorization" not in sent_headers


async def test_health_check_true_when_reachable(provider):
    with respx.mock(assert_all_called=True) as mock:
        mock.get(f"{BASE_URL}/models").mock(return_value=httpx.Response(200, json={"data": []}))
        assert await provider.health_check() is True


async def test_health_check_false_on_error_status(provider):
    with respx.mock(assert_all_called=True) as mock:
        mock.get(f"{BASE_URL}/models").mock(return_value=httpx.Response(500))
        assert await provider.health_check() is False


async def test_health_check_false_on_connection_error(provider):
    with respx.mock(assert_all_called=True) as mock:
        mock.get(f"{BASE_URL}/models").mock(side_effect=httpx.ConnectError("boom"))
        assert await provider.health_check() is False
