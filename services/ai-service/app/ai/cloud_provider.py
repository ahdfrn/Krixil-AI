import json
from collections.abc import AsyncIterator

import httpx

from app.ai.base import ModelMessage, ModelProvider, ModelResponse, ToolCallRequest, ToolSchema
from app.core.config import Settings


class CloudModelProvider(ModelProvider):
    """OpenAI-compatible provider over HTTP. Works against api.openai.com or any endpoint that
    speaks the same /chat/completions, /embeddings, /models shape (self-hosted vLLM, OpenRouter,
    etc.) — nothing here is OpenAI-specific beyond the request/response shape itself."""

    name = "openai"

    def __init__(self, settings: Settings):
        self._model = settings.openai_model
        self._embedding_model = settings.openai_embedding_model
        self._client = httpx.AsyncClient(
            base_url=settings.openai_base_url,
            headers={"Authorization": f"Bearer {settings.openai_api_key}"},
            timeout=httpx.Timeout(60.0, connect=10.0),
        )

    async def aclose(self) -> None:
        await self._client.aclose()

    @staticmethod
    def _to_openai_messages(messages: list[ModelMessage]) -> list[dict]:
        return [{"role": m.role, "content": m.content} for m in messages]

    async def generate(self, messages: list[ModelMessage], **kwargs) -> ModelResponse:
        response = await self._client.post(
            "/chat/completions",
            json={"model": self._model, "messages": self._to_openai_messages(messages), **kwargs},
        )
        response.raise_for_status()
        data = response.json()
        content = data["choices"][0]["message"]["content"]
        return ModelResponse(content=content, model=data.get("model", self._model), usage=data.get("usage", {}))

    async def stream(self, messages: list[ModelMessage], **kwargs) -> AsyncIterator[str]:
        payload = {
            "model": self._model,
            "messages": self._to_openai_messages(messages),
            "stream": True,
            **kwargs,
        }
        async with self._client.stream("POST", "/chat/completions", json=payload) as response:
            response.raise_for_status()
            async for line in response.aiter_lines():
                if not line.startswith("data: "):
                    continue
                data = line[len("data: "):]
                if data == "[DONE]":
                    break
                chunk = json.loads(data)
                delta = chunk["choices"][0].get("delta", {})
                content = delta.get("content")
                if content:
                    yield content

    async def embeddings(self, texts: list[str]) -> list[list[float]]:
        response = await self._client.post(
            "/embeddings", json={"model": self._embedding_model, "input": texts}
        )
        response.raise_for_status()
        data = response.json()["data"]
        return [item["embedding"] for item in data]

    async def tool_call(
        self, messages: list[ModelMessage], tools: list[ToolSchema], **kwargs
    ) -> ModelResponse:
        payload = {
            "model": self._model,
            "messages": self._to_openai_messages(messages),
            "tools": [
                {
                    "type": "function",
                    "function": {"name": t.name, "description": t.description, "parameters": t.parameters},
                }
                for t in tools
            ],
            **kwargs,
        }
        response = await self._client.post("/chat/completions", json=payload)
        response.raise_for_status()
        data = response.json()
        message = data["choices"][0]["message"]

        tool_calls = [
            ToolCallRequest(name=tc["function"]["name"], arguments=json.loads(tc["function"]["arguments"]))
            for tc in (message.get("tool_calls") or [])
        ]
        return ModelResponse(
            content=message.get("content") or "",
            model=data.get("model", self._model),
            usage=data.get("usage", {}),
            tool_calls=tool_calls,
        )

    async def health_check(self) -> bool:
        try:
            response = await self._client.get("/models")
            return response.status_code == 200
        except httpx.HTTPError:
            return False
