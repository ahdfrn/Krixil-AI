from collections.abc import Callable

from app.ai.base import ModelProvider
from app.ai.cloud_provider import CloudModelProvider
from app.ai.mock_provider import MockProvider
from app.core.config import get_settings

# Factories, not instances: MockProvider is free to construct, but CloudModelProvider opens an
# httpx connection pool — that only happens if "openai" is actually selected, and only once
# (cached in _instances below), not for every request or at import time.
_PROVIDER_FACTORIES: dict[str, Callable[[], ModelProvider]] = {
    "mock": lambda: MockProvider(),
    "openai": lambda: CloudModelProvider(get_settings()),
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
