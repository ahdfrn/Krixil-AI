from collections.abc import Callable

from app.ai.anthropic_provider import AnthropicModelProvider
from app.ai.base import ModelProvider
from app.ai.cloud_provider import CloudModelProvider
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
    # OpenRouter and Groq are both genuinely OpenAI-compatible for chat *and* embeddings (see
    # config.py's comments) — no embeddings_provider override needed, unlike anthropic/huggingface.
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
        embedding_model=get_settings().groq_embedding_model,
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


class ModelRouter:
    """Resolves the configured provider by name. Providers register a factory in
    _PROVIDER_FACTORIES behind the same ModelProvider ABC — no caller of get_provider() needs to
    change when a new one is added."""

    def get_provider(self) -> ModelProvider:
        settings = get_settings()
        name = settings.model_provider

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
