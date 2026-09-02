import json
from collections.abc import AsyncIterator

import httpx
import pytest
import respx

from app.ai.base import ModelMessage, ModelProvider, ModelResponse, ToolSchema
from app.ai.cloud_provider import CloudModelProvider

BASE_URL = "https://mock.openai.test/v1"


@pytest.fixture
async def provider():
    p = CloudModelProvider(
        name="openai",
        base_url=BASE_URL,
        api_key="test-key",
        model="test-model",
        embedding_model="test-embed-model",
    )
    yield p
    await p.aclose()


class _FakeEmbeddingsProvider(ModelProvider):
    """Same role as AnthropicModelProvider's own test double (test_anthropic_provider.py) — stands
    in for a real embeddings delegate so these tests check "delegates when given one", not any
    particular embeddings shape."""

    name = "fake-embeddings"

    def __init__(self):
        self.calls: list[list[str]] = []
        self.closed = False

    async def generate(self, messages, **kwargs) -> ModelResponse:  # pragma: no cover - unused
        raise NotImplementedError

    def stream(self, messages, **kwargs) -> AsyncIterator[str]:  # pragma: no cover - unused
        raise NotImplementedError

    async def embeddings(self, texts: list[str]) -> list[list[float]]:
        self.calls.append(texts)
        return [[0.9, 0.9] for _ in texts]

    async def tool_call(self, messages, tools, **kwargs) -> ModelResponse:  # pragma: no cover
        raise NotImplementedError

    async def health_check(self) -> bool:  # pragma: no cover - unused
        return True

    async def aclose(self) -> None:
        self.closed = True


async def test_generate_returns_content_and_usage(provider):
    with respx.mock(assert_all_called=True) as mock:
        mock.post(f"{BASE_URL}/chat/completions").mock(
            return_value=httpx.Response(
                200,
                json={
                    "model": "test-model",
                    "choices": [{"message": {"content": "Hello there"}}],
                    "usage": {"prompt_tokens": 5, "completion_tokens": 3},
                },
            )
        )
        response = await provider.generate([ModelMessage(role="user", content="hi")])

    assert response.content == "Hello there"
    assert response.model == "test-model"
    assert response.usage == {"prompt_tokens": 5, "completion_tokens": 3}


async def test_generate_raises_on_http_error(provider):
    with respx.mock(assert_all_called=True) as mock:
        mock.post(f"{BASE_URL}/chat/completions").mock(return_value=httpx.Response(401))
        with pytest.raises(httpx.HTTPStatusError):
            await provider.generate([ModelMessage(role="user", content="hi")])


async def test_stream_yields_content_deltas(provider):
    sse_body = (
        'data: {"choices":[{"delta":{"content":"Hello"}}]}\n\n'
        'data: {"choices":[{"delta":{"content":" world"}}]}\n\n'
        "data: [DONE]\n\n"
    )
    with respx.mock(assert_all_called=True) as mock:
        mock.post(f"{BASE_URL}/chat/completions").mock(
            return_value=httpx.Response(
                200, content=sse_body.encode(), headers={"content-type": "text/event-stream"}
            )
        )
        chunks = [
            delta async for delta in provider.stream([ModelMessage(role="user", content="hi")])
        ]

    assert chunks == ["Hello", " world"]


async def test_embeddings_returns_vectors(provider):
    with respx.mock(assert_all_called=True) as mock:
        mock.post(f"{BASE_URL}/embeddings").mock(
            return_value=httpx.Response(
                200, json={"data": [{"embedding": [0.1, 0.2]}, {"embedding": [0.3, 0.4]}]}
            )
        )
        result = await provider.embeddings(["a", "b"])

    assert result == [[0.1, 0.2], [0.3, 0.4]]


async def test_embeddings_delegates_when_given_an_embeddings_provider():
    # Hugging Face's router is chat-only — this is the mechanism that keeps its embeddings() call
    # from ever hitting a /embeddings endpoint that doesn't speak this shape.
    fake = _FakeEmbeddingsProvider()
    p = CloudModelProvider(
        name="huggingface",
        base_url=BASE_URL,
        api_key="test-key",
        model="test-model",
        embedding_model="unused",
        embeddings_provider=fake,
    )
    try:
        with respx.mock(assert_all_called=False) as mock:
            route = mock.post(f"{BASE_URL}/embeddings")
            result = await p.embeddings(["a", "b"])
            assert route.call_count == 0  # never called its own endpoint
    finally:
        await p.aclose()

    assert result == [[0.9, 0.9], [0.9, 0.9]]
    assert fake.calls == [["a", "b"]]


async def test_aclose_also_closes_the_embeddings_provider():
    fake = _FakeEmbeddingsProvider()
    p = CloudModelProvider(
        name="huggingface",
        base_url=BASE_URL,
        api_key="test-key",
        model="test-model",
        embedding_model="unused",
        embeddings_provider=fake,
    )
    await p.aclose()
    assert fake.closed is True


async def test_tool_call_sends_tools_and_parses_structured_call(provider):
    tool = ToolSchema(
        name="knowledge.search", description="Search docs", parameters={"type": "object"}
    )

    with respx.mock(assert_all_called=True) as mock:
        route = mock.post(f"{BASE_URL}/chat/completions").mock(
            return_value=httpx.Response(
                200,
                json={
                    "model": "test-model",
                    "choices": [
                        {
                            "message": {
                                "content": None,
                                "tool_calls": [
                                    {
                                        "function": {
                                            "name": "knowledge.search",
                                            "arguments": json.dumps({"query": "pgvector"}),
                                        }
                                    }
                                ],
                            }
                        }
                    ],
                    "usage": {"prompt_tokens": 10, "completion_tokens": 4},
                },
            )
        )
        response = await provider.tool_call(
            [ModelMessage(role="user", content="search for pgvector")], [tool]
        )

    sent_body = json.loads(route.calls.last.request.content)
    assert sent_body["tools"][0]["function"]["name"] == "knowledge.search"

    assert response.content == ""
    assert len(response.tool_calls) == 1
    assert response.tool_calls[0].name == "knowledge.search"
    assert response.tool_calls[0].arguments == {"query": "pgvector"}


async def test_tool_call_with_no_tool_calls_returns_plain_content(provider):
    with respx.mock(assert_all_called=True) as mock:
        mock.post(f"{BASE_URL}/chat/completions").mock(
            return_value=httpx.Response(
                200,
                json={
                    "model": "test-model",
                    "choices": [{"message": {"content": "just an answer"}}],
                },
            )
        )
        response = await provider.tool_call([ModelMessage(role="user", content="hi")], [])

    assert response.content == "just an answer"
    assert response.tool_calls == []


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
