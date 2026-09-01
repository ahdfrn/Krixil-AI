import pytest

import app.ai.router as router_module
from app.ai.anthropic_provider import AnthropicModelProvider
from app.ai.catalog import get_model_catalog
from app.ai.router import ModelRouter
from app.core.config import Settings


def test_anthropic_provider_requires_api_key(monkeypatch):
    router = ModelRouter()
    monkeypatch.setattr(
        "app.ai.router.get_settings",
        lambda: Settings(model_provider="anthropic", anthropic_api_key=""),
    )
    with pytest.raises(ValueError, match="ANTHROPIC_API_KEY"):
        router.get_provider()


async def test_anthropic_provider_resolves_with_a_real_key(monkeypatch):
    # get_provider() caches instances in the module-level _instances dict, keyed only by provider
    # name — real housekeeping needed here, not just closing the local reference, or a later test
    # (any test, in any file, same pytest process) that resolves "anthropic" again would get back
    # this same now-closed httpx client instead of a fresh one.
    router = ModelRouter()
    monkeypatch.setattr(
        "app.ai.router.get_settings",
        lambda: Settings(model_provider="anthropic", anthropic_api_key="sk-ant-test"),
    )
    try:
        provider = router.get_provider()
        assert isinstance(provider, AnthropicModelProvider)
        assert provider.name == "anthropic"
    finally:
        cached = router_module._instances.pop("anthropic", None)
        if cached is not None:
            await cached.aclose()  # type: ignore[attr-defined]


async def test_anthropic_catalog_entry_names_the_configured_model():
    settings = Settings(model_provider="anthropic", anthropic_model="claude-opus-5")
    catalog = await get_model_catalog(settings)
    assert len(catalog) == 1
    assert catalog[0].id == "auto"
    assert "claude-opus-5" in catalog[0].description
