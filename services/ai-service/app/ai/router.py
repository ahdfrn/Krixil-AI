from collections.abc import Callable

from app.ai.anthropic_provider import AnthropicModelProvider
from app.ai.base import ModelProvider
from app.ai.cloud_provider import CloudModelProvider
from app.ai.fallback import FallbackProvider
from app.ai.mock_provider import MockProvider
from app.core.config import get_settings


def _ollama_provider() -> CloudModelProvider:
    # Ollama needs no real API key — it ignores the Authorization header entirely, but the HTTP
    # client still needs some non-empty value to send. Also reused as AnthropicModelProvider's
    # embeddings backend below, since Anthropic has no embeddings endpoint of its own.
    return CloudModelProvider(
        name="ollama",
        base_url=get_settings().ollama_base_url,
        api_key="ollama",
        model=get_settings().ollama_default_model,
        embedding_model=get_settings().ollama_embedding_model,
    )


# Factories, not instances: MockProvider is free to construct, but CloudModelProvider/
# AnthropicModelProvider open an httpx connection pool — that only happens if actually selected,
# and only once (cached in _instances below), not for every request or at import time.
_PROVIDER_FACTORIES: dict[str, Callable[[], ModelProvider]] = {
    "mock": lambda: MockProvider(),
    "openai": lambda: CloudModelProvider(
        name="openai",
        base_url=get_settings().openai_base_url,
        api_key=get_settings().openai_api_key,
        model=get_settings().openai_model,
        embedding_model=get_settings().openai_embedding_model,
    ),
    "ollama": _ollama_provider,
    "anthropic": lambda: AnthropicModelProvider(
        api_key=get_settings().anthropic_api_key,
        base_url=get_settings().anthropic_base_url,
        model=get_settings().anthropic_model,
        api_version=get_settings().anthropic_api_version,
        max_tokens=get_settings().anthropic_max_tokens,
        embeddings_provider=_ollama_provider(),
    ),
    # OpenRouter supports its own embedding endpoint. Groq chat uses local Ollama embeddings.
    "openrouter": lambda: CloudModelProvider(
        name="openrouter",
        base_url=get_settings().openrouter_base_url,
        api_key=get_settings().openrouter_api_key,
        model=get_settings().openrouter_model,
        embedding_model=get_settings().openrouter_embedding_model,
    ),
    "groq": lambda: CloudModelProvider(
        name="groq",
        base_url=get_settings().groq_base_url,
        api_key=get_settings().groq_api_key,
        model=get_settings().groq_model,
        embedding_model="",
        embeddings_provider=_ollama_provider(),
    ),
    # Hugging Face's router is chat-only (OpenAI-compatible) — real embeddings delegated to
    # Ollama, same reasoning and same pattern as "anthropic" above.
    "huggingface": lambda: CloudModelProvider(
        name="huggingface",
        base_url=get_settings().huggingface_base_url,
        api_key=get_settings().huggingface_api_key,
        model=get_settings().huggingface_model,
        embedding_model="",
        embeddings_provider=_ollama_provider(),
    ),
}

_instances: dict[str, ModelProvider] = {}
_fallback_instances: dict[tuple, FallbackProvider] = {}


class ModelRouter:
    """Resolves the configured provider by name. Providers register a factory in
    _PROVIDER_FACTORIES behind the same ModelProvider ABC — no caller of get_provider() needs to
    change when a new one is added."""

    def get_provider(self) -> ModelProvider:
        settings = get_settings()
        names = list(
            dict.fromkeys(
                [
                    settings.model_provider,
                    *[
                        name.strip()
                        for name in settings.model_fallback_providers.split(",")
                        if name.strip()
                    ],
                ]
            )
        )
        providers = [self._get_named_provider(name) for name in names]
        if len(providers) == 1:
            return providers[0]
        if "mock" in names:
            raise ValueError("Mock provider cannot participate in a real fallback chain")
        cooldown = settings.model_fallback_cooldown_seconds
        quota_cooldown = settings.model_fallback_quota_cooldown_seconds
        if cooldown <= 0 or quota_cooldown <= 0:
            raise ValueError("Fallback cooldowns must be positive")
        key = (*[id(provider) for provider in providers], cooldown, quota_cooldown)
        if key not in _fallback_instances:
            _fallback_instances[key] = FallbackProvider(providers, cooldown, quota_cooldown)
        return _fallback_instances[key]

    def _get_named_provider(self, name: str) -> ModelProvider:
        settings = get_settings()

        if name not in _PROVIDER_FACTORIES:
            available = ", ".join(sorted(_PROVIDER_FACTORIES))
            raise ValueError(f"Unknown MODEL_PROVIDER '{name}'. Available: {available}")

        if name == "openai" and not settings.openai_api_key:
            raise ValueError("MODEL_PROVIDER=openai requires OPENAI_API_KEY to be set")

        if name == "anthropic" and not settings.anthropic_api_key:
            raise ValueError("MODEL_PROVIDER=anthropic requires ANTHROPIC_API_KEY to be set")

        if name == "openrouter" and not settings.openrouter_api_key:
            raise ValueError("MODEL_PROVIDER=openrouter requires OPENROUTER_API_KEY to be set")

        if name == "groq" and not settings.groq_api_key:
            raise ValueError("MODEL_PROVIDER=groq requires GROQ_API_KEY to be set")

        if name == "huggingface" and not settings.huggingface_api_key:
            raise ValueError("MODEL_PROVIDER=huggingface requires HUGGINGFACE_API_KEY to be set")

        if name not in _instances:
            _instances[name] = _PROVIDER_FACTORIES[name]()
        return _instances[name]


async def aclose_providers() -> None:
    """Called from the app's shutdown lifespan to release any open HTTP connections."""
    for provider in _instances.values():
        aclose = getattr(provider, "aclose", None)
        if aclose is not None:
            await aclose()
    _instances.clear()
    _fallback_instances.clear()
