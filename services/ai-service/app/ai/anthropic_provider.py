import json
from collections.abc import AsyncIterator

import httpx

from app.ai.base import ModelMessage, ModelProvider, ModelResponse, ToolCallRequest, ToolSchema


class AnthropicModelProvider(ModelProvider):
    """Anthropic's real Messages API (api.anthropic.com/v1/messages) — deliberately not built on
    CloudModelProvider (app/ai/cloud_provider.py) the way "openai"/"ollama" are, because this API
    genuinely isn't OpenAI-compatible: the system prompt is a top-level `system` field, not a
    message with role="system"; auth is `x-api-key` + `anthropic-version` headers, not
    `Authorization: Bearer`; tool use comes back as `content` blocks (`type: "tool_use"`), not a
    `tool_calls` array; there's no `/embeddings` endpoint at all.
    """

    name = "anthropic"

    def __init__(
        self,
        *,
        api_key: str,
        base_url: str,
        model: str,
        api_version: str,
        max_tokens: int,
        embeddings_provider: ModelProvider,
    ):
        self._model = model
        self._max_tokens = max_tokens
        self._client = httpx.AsyncClient(
            base_url=base_url,
            headers={
                "x-api-key": api_key,
                "anthropic-version": api_version,
                "content-type": "application/json",
            },
            timeout=httpx.Timeout(60.0, connect=10.0),
        )
        # Anthropic has no embeddings endpoint of its own — RAG/knowledge search keeps using a
        # real embedding model regardless of which provider chat/tool_call go through (see
        # app/ai/router.py: this is always the same Ollama-backed provider "ollama" itself uses).
        self._embeddings_provider = embeddings_provider

    async def aclose(self) -> None:
        await self._client.aclose()
        aclose = getattr(self._embeddings_provider, "aclose", None)
        if aclose is not None:
            await aclose()

    @staticmethod
    def _split_system(messages: list[ModelMessage]) -> tuple[str | None, list[dict]]:
        """Anthropic doesn't accept role="system" inside the `messages` array at all — it has to
        be lifted out into its own top-level field. Every ModelMessage list this app builds
        starts with exactly one system message (see app/agents/prompts.py's SYSTEM_PROMPT usage),
        but this joins multiple if there ever were more, rather than silently dropping any."""
        system_parts = [m.content for m in messages if m.role == "system"]
        system = "\n\n".join(system_parts) if system_parts else None
        rest = [{"role": m.role, "content": m.content} for m in messages if m.role != "system"]
        return system, rest

    def _usage(self, data: dict) -> dict:
        raw = data.get("usage", {})
        return {
            "prompt_tokens": raw.get("input_tokens", 0),
            "completion_tokens": raw.get("output_tokens", 0),
        }

    async def generate(self, messages: list[ModelMessage], **kwargs) -> ModelResponse:
        system, anthropic_messages = self._split_system(messages)
        payload: dict = {
            "model": self._model,
            "max_tokens": self._max_tokens,
            "messages": anthropic_messages,
            **kwargs,
        }
        if system:
            payload["system"] = system
        response = await self._client.post("/messages", json=payload)
        response.raise_for_status()
        data = response.json()
        text = "".join(
            block["text"] for block in data.get("content", []) if block.get("type") == "text"
        )
        return ModelResponse(
            content=text, model=data.get("model", self._model), usage=self._usage(data)
        )

    async def stream(self, messages: list[ModelMessage], **kwargs) -> AsyncIterator[str]:
        system, anthropic_messages = self._split_system(messages)
        payload: dict = {
            "model": self._model,
            "max_tokens": self._max_tokens,
            "messages": anthropic_messages,
            "stream": True,
            **kwargs,
        }
        if system:
            payload["system"] = system
        async with self._client.stream("POST", "/messages", json=payload) as response:
            response.raise_for_status()
            async for line in response.aiter_lines():
                if not line.startswith("data: "):
                    continue
                event = json.loads(line[len("data: ") :])
                if event.get("type") != "content_block_delta":
                    continue
                delta = event.get("delta", {})
                if delta.get("type") == "text_delta":
                    yield delta.get("text", "")

    async def embeddings(self, texts: list[str]) -> list[list[float]]:
        return await self._embeddings_provider.embeddings(texts)

    async def tool_call(
        self, messages: list[ModelMessage], tools: list[ToolSchema], **kwargs
    ) -> ModelResponse:
        system, anthropic_messages = self._split_system(messages)
        payload: dict = {
            "model": self._model,
            "max_tokens": self._max_tokens,
            "messages": anthropic_messages,
            "tools": [
                {"name": t.name, "description": t.description, "input_schema": t.parameters}
                for t in tools
            ],
            **kwargs,
        }
        if system:
            payload["system"] = system
        response = await self._client.post("/messages", json=payload)
        response.raise_for_status()
        data = response.json()
        content = data.get("content", [])

        text = "".join(block["text"] for block in content if block.get("type") == "text")
        tool_calls = [
            ToolCallRequest(name=block["name"], arguments=block.get("input", {}))
            for block in content
            if block.get("type") == "tool_use"
        ]
        return ModelResponse(
            content=text,
            model=data.get("model", self._model),
            usage=self._usage(data),
            tool_calls=tool_calls,
        )

    async def health_check(self) -> bool:
        try:
            response = await self._client.get("/models")
            return response.status_code == 200
        except httpx.HTTPError:
            return False
