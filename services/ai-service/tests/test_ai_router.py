from unittest.mock import AsyncMock

import pytest

import app.ai.router as router_module
from app.ai.anthropic_provider import AnthropicModelProvider
from app.ai.catalog import get_model_catalog
from app.ai.cloud_provider import CloudModelProvider
from app.ai.router import ModelRouter
from app.core.config import Settings


async def test_groq_delegates_embeddings_to_ollama(monkeypatch):
    settings = Settings(model_provider="groq", groq_api_key="test-key", model_fallback_providers="")
    monkeypatch.setattr(router_module, "get_settings", lambda: settings)
    local = AsyncMock()
    local.embeddings.return_value = [[0.1, 0.2]]
    monkeypatch.setattr(router_module, "_ollama_provider", lambda: local)
    monkeypatch.setattr(router_module, "_instances", {})
    try:
        provider = ModelRouter().get_provider()
        assert await provider.embeddings(["test"]) == [[0.1, 0.2]]
        local.embeddings.assert_awaited_once_with(["test"])
    finally:
        await router_module.aclose_providers()


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


@pytest.mark.parametrize(
    ("provider_name", "key_field", "env_name"),
    [
        ("openrouter", "openrouter_api_key", "OPENROUTER_API_KEY"),
        ("groq", "groq_api_key", "GROQ_API_KEY"),
        ("huggingface", "huggingface_api_key", "HUGGINGFACE_API_KEY"),
    ],
)
def test_cloud_provider_requires_api_key(monkeypatch, provider_name, key_field, env_name):
    router = ModelRouter()
    monkeypatch.setattr(
        "app.ai.router.get_settings",
        lambda: Settings(model_provider=provider_name, **{key_field: ""}),
    )
    with pytest.raises(ValueError, match=env_name):
        router.get_provider()


@pytest.mark.parametrize(
    ("provider_name", "key_field"),
    [
        ("openrouter", "openrouter_api_key"),
        ("groq", "groq_api_key"),
        ("huggingface", "huggingface_api_key"),
    ],
)
async def test_cloud_provider_resolves_with_a_real_key(monkeypatch, provider_name, key_field):
    # Same real housekeeping as test_anthropic_provider_resolves_with_a_real_key above — the
    # module-level _instances cache is keyed by name only, so a leaked open client here would
    # bleed into whatever test resolves this provider name next.
    router = ModelRouter()
    monkeypatch.setattr(
        "app.ai.router.get_settings",
        lambda: Settings(model_provider=provider_name, **{key_field: "test-key"}),
    )
    try:
        provider = router.get_provider()
        assert isinstance(provider, CloudModelProvider)
        assert provider.name == provider_name
    finally:
        cached = router_module._instances.pop(provider_name, None)
        if cached is not None:
            await cached.aclose()  # type: ignore[attr-defined]


async def test_openrouter_catalog_entry_names_the_configured_model():
    settings = Settings(model_provider="openrouter", openrouter_model="anthropic/claude-sonnet-5")
    catalog = await get_model_catalog(settings)
    assert len(catalog) == 1
    assert catalog[0].id == "auto"
    assert "anthropic/claude-sonnet-5" in catalog[0].description


async def test_groq_catalog_entry_names_the_configured_model():
    settings = Settings(model_provider="groq", groq_model="llama-3.3-70b-versatile")
    catalog = await get_model_catalog(settings)
    assert len(catalog) == 1
    assert "llama-3.3-70b-versatile" in catalog[0].description


async def test_huggingface_catalog_entry_names_the_configured_model():
    settings = Settings(
        model_provider="huggingface", huggingface_model="meta-llama/Llama-3.1-8B-Instruct"
    )
    catalog = await get_model_catalog(settings)
    assert len(catalog) == 1
    assert "meta-llama/Llama-3.1-8B-Instruct" in catalog[0].description
