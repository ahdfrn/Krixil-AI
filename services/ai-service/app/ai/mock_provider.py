import asyncio
import hashlib
import random
import re
from collections.abc import AsyncIterator

from app.ai.base import ModelMessage, ModelProvider, ModelResponse, ToolCallRequest, ToolSchema
from app.core.config import get_settings

_UUID_RE = re.compile(r"[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}")


def _pseudo_embedding(text: str, dim: int) -> list[float]:
    """Deterministic, text-dependent fake vector — same text always maps to the same vector, and
    different texts differ, so similarity search behaves plausibly even against mock embeddings."""
    seed = int(hashlib.sha256(text.encode()).hexdigest(), 16)
    rng = random.Random(seed)
    return [rng.uniform(-1.0, 1.0) for _ in range(dim)]


def _matches_tool(tool_name: str, lowered_message: str) -> bool:
    # \b word-boundary, not a plain substring check: "document" must not match inside
    # "document_id" (e.g. when the message is actually an error echoing a field name back) —
    # underscore counts as a word character, so \b already won't cross it, but be explicit that
    # this is intentional rather than an accident of the regex.
    words = [w for w in re.split(r"[._]", tool_name) if len(w) > 3]
    return any(re.search(rf"\b{re.escape(word)}\b", lowered_message) for word in words)


def _guess_arguments(parameters: dict, message: str) -> dict:
    """No real reasoning here — just enough to fill a tool's *required* fields plausibly from the
    raw message, so the mock provider can demonstrate the agent loop without an API key. A
    required field this can't guess (anything but a string or a UUID) is simply left unset, which
    correctly fails schema validation downstream rather than inventing a wrong value."""
    properties = parameters.get("properties", {})
    arguments: dict = {}
    for field_name in parameters.get("required", []):
        schema = properties.get(field_name, {})
        if schema.get("format") == "uuid":
            match = _UUID_RE.search(message)
            if match:
                arguments[field_name] = match.group(0)
        elif schema.get("type") == "string":
            arguments[field_name] = message
    return arguments


class MockProvider(ModelProvider):
    """Deterministic, offline provider — no network calls, no API key. Used as the Phase 0
    default so the app is fully runnable and testable before a real provider is wired up."""

    name = "mock"

    async def generate(self, messages: list[ModelMessage], **kwargs) -> ModelResponse:
        last_user = next((m.content for m in reversed(messages) if m.role == "user"), "")
        content = f"Mock response to: {last_user}" if last_user else "Mock response."
        usage = {"prompt_tokens": len(messages), "completion_tokens": len(content.split())}
        return ModelResponse(content=content, model=self.name, usage=usage)

    async def stream(self, messages: list[ModelMessage], **kwargs) -> AsyncIterator[str]:
        response = await self.generate(messages, **kwargs)
        for word in response.content.split(" "):
            yield word + " "
            await asyncio.sleep(0)

    async def embeddings(self, texts: list[str]) -> list[list[float]]:
        dim = get_settings().embedding_dimension
        return [_pseudo_embedding(text, dim) for text in texts]

    async def tool_call(
        self, messages: list[ModelMessage], tools: list[ToolSchema], **kwargs
    ) -> ModelResponse:
        last_user = next((m.content for m in reversed(messages) if m.role == "user"), "")
        lowered = last_user.lower()

        for tool in tools:
            if _matches_tool(tool.name, lowered):
                arguments = _guess_arguments(tool.parameters, last_user)
                return ModelResponse(
                    content="",
                    model=self.name,
                    tool_calls=[ToolCallRequest(name=tool.name, arguments=arguments)],
                )

        content = f"Mock final answer to: {last_user}" if last_user else "Mock final answer."
        return ModelResponse(content=content, model=self.name)

    async def health_check(self) -> bool:
        return True
