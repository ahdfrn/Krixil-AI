import json

import httpx
import pytest
import respx

from app.ai.base import ModelMessage, ToolSchema
from app.ai.cloud_provider import CloudModelProvider
from app.core.config import Settings

BASE_URL = "https://mock.openai.test/v1"


@pytest.fixture
async def provider():
    settings = Settings(
        openai_api_key="test-key",
        openai_base_url=BASE_URL,
        openai_model="test-model",
        openai_embedding_model="test-embed-model",
    )
    p = CloudModelProvider(settings)
    yield p
    await p.aclose()


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
        chunks = [delta async for delta in provider.stream([ModelMessage(role="user", content="hi")])]

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


async def test_tool_call_sends_tools_and_parses_structured_call(provider):
    tool = ToolSchema(name="knowledge.search", description="Search docs", parameters={"type": "object"})

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
        response = await provider.tool_call([ModelMessage(role="user", content="search for pgvector")], [tool])

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
                json={"model": "test-model", "choices": [{"message": {"content": "just an answer"}}]},
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
