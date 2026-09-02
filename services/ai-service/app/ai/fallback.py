"""Retry model inference only; never retry the agent loop or tool execution."""

import time
from collections.abc import AsyncIterator
from email.utils import parsedate_to_datetime

import httpx

from app.ai.base import ModelMessage, ModelProvider, ModelResponse, ToolSchema
from app.core.logging import get_logger

logger = get_logger(__name__)


class ProvidersUnavailable(RuntimeError):
    """Safe to show to users: contains no upstream payloads, prompts, or credentials."""


class FallbackProvider(ModelProvider):
    name = "fallback"

    def __init__(
        self, providers: list[ModelProvider], cooldown: int = 60, quota_cooldown: int = 3600
    ):
        self.providers = providers
        self.cooldown = cooldown
        self.quota_cooldown = quota_cooldown
        # Shared by requests in this process, but not by distinct explicit primary models.
        self.unavailable_until: dict[tuple[str, str], float] = {}

    def _delay(self, error: Exception) -> float | None:
        if isinstance(error, httpx.TimeoutException | httpx.NetworkError):
            return self.cooldown
        if not isinstance(error, httpx.HTTPStatusError):
            return None
        response = error.response
        if response.status_code not in {402, 429, 500, 502, 503, 504}:
            return None  # Authentication, bad arguments, context overflow: don't mask bugs.
        delay: float = self.quota_cooldown if response.status_code == 402 else self.cooldown
        if response.status_code == 429:
            try:
                code = response.json().get("error", {}).get("code")
                if code in {"insufficient_quota", "quota_exceeded", "daily_limit_exceeded"}:
                    delay = self.quota_cooldown
            except (ValueError, AttributeError):
                pass
        retry_after = response.headers.get("retry-after")
        if retry_after:
            try:
                delay = max(delay, float(retry_after))
            except ValueError:
                try:
                    delay = max(delay, parsedate_to_datetime(retry_after).timestamp() - time.time())
                except (ValueError, TypeError, OverflowError):
                    pass
        return delay

    def _candidates(self, kwargs):
        for index, provider in enumerate(self.providers):
            options = dict(kwargs)
            if index > 0:
                # A local model ID is not a valid cloud model ID (and vice versa).
                options.pop("model", None)
            key = (provider.name, str(options.get("model") or "default"))
            if self.unavailable_until.get(key, 0) <= time.monotonic():
                yield provider, options, key

    def _failed(self, provider, key, error):
        delay = self._delay(error)
        if delay is None:
            raise error
        self.unavailable_until[key] = time.monotonic() + delay
        logger.warning("model_provider_unavailable", provider=provider.name, retry_in_seconds=delay)

    def _exhausted(self):
        return ProvidersUnavailable(
            "All configured model providers are unavailable or cooling down. "
            "No further tool was executed for this model request. Retry after quota reset."
        )

    async def _request(self, method, messages, tools=None, **kwargs):
        for provider, options, key in self._candidates(kwargs):
            try:
                if method == "tool_call":
                    result = await provider.tool_call(messages, tools, **options)
                else:
                    result = await provider.generate(messages, **options)
            except Exception as error:
                self._failed(provider, key, error)
                continue
            if provider is not self.providers[0]:
                logger.info("model_fallback_selected", provider=provider.name, model=result.model)
            result.provider = provider.name
            return result
        raise self._exhausted()

    async def generate(self, messages: list[ModelMessage], **kwargs) -> ModelResponse:
        return await self._request("generate", messages, **kwargs)

    async def tool_call(
        self, messages: list[ModelMessage], tools: list[ToolSchema], **kwargs
    ) -> ModelResponse:
        return await self._request("tool_call", messages, tools, **kwargs)

    async def stream(self, messages: list[ModelMessage], **kwargs) -> AsyncIterator[str]:
        for provider, options, key in self._candidates(kwargs):
            emitted = False
            try:
                async for chunk in provider.stream(messages, **options):
                    if chunk:
                        emitted = True
                    yield chunk
                return
            except Exception as error:
                self._failed(provider, key, error)
                if emitted:
                    # Never append a second answer to a partially delivered first answer.
                    raise
        raise self._exhausted()

    async def embeddings(self, texts: list[str]) -> list[list[float]]:
        # Switching vector spaces silently would corrupt similarity search.
        return await self.providers[0].embeddings(texts)

    async def health_check(self) -> bool:
        for provider, _, _ in self._candidates({}):
            if await provider.health_check():
                return True
        return False
