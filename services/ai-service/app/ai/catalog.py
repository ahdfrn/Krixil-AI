import httpx
from fastapi import HTTPException, status

from app.core.config import Settings, get_settings
from app.schemas.model import ModelOut


async def _ollama_models(settings: Settings) -> list[ModelOut]:
    """Queries Ollama's own /api/tags for exactly what's actually pulled, rather than a config
    value that could drift out of sync with reality — same "no fabricated catalog entries"
    discipline as the rest of this catalog. Excludes the embedding model, which isn't a chat model
    and shouldn't be user-selectable. Returns [] (not an error) if Ollama isn't reachable — /models
    should degrade gracefully, not 500, since it's just a UI listing."""
    native_base = settings.ollama_base_url.removesuffix("/v1")
    try:
        async with httpx.AsyncClient(base_url=native_base, timeout=5.0) as client:
            response = await client.get("/api/tags")
            response.raise_for_status()
            tags = response.json().get("models", [])
    except httpx.HTTPError:
        return []

    return [
        ModelOut(
            id=tag["name"],
            name=tag["name"],
            description="Local model served by Ollama on your machine.",
        )
        for tag in tags
        if tag["name"] != settings.ollama_embedding_model
        and not tag["name"].startswith(f"{settings.ollama_embedding_model}:")
    ]


async def get_model_catalog(settings: Settings | None = None) -> list[ModelOut]:
    """"auto" always exists and routes to the active provider's own default — this keeps existing
    frontend sessions (whose persisted selectedModel defaults to "auto") working across a provider
    change. For "ollama", real pulled models are listed alongside it (see _ollama_models); for
    "openai"/"mock" there's still only ever the one real entry, since ModelRouter resolves exactly
    one provider for those — not a catalog of fabricated named variants."""
    settings = settings or get_settings()

    if settings.model_provider == "ollama":
        auto = ModelOut(
            id="auto",
            name="Krixil Auto",
            description=f"Routes to {settings.ollama_default_model} (your default local model).",
        )
        return [auto, *await _ollama_models(settings)]

    if settings.model_provider == "openai":
        description = (
            f"Routes to {settings.openai_model} via the configured OpenAI-compatible endpoint."
        )
    elif settings.model_provider == "anthropic":
        description = f"Routes to {settings.anthropic_model} via the Anthropic API."
    elif settings.model_provider == "openrouter":
        description = f"Routes to {settings.openrouter_model} via OpenRouter."
    elif settings.model_provider == "groq":
        description = f"Routes to {settings.groq_model} via Groq."
    elif settings.model_provider == "huggingface":
        description = (
            f"Routes to {settings.huggingface_model} via Hugging Face's Inference Providers router."
        )
    else:
        description = (
            "Routes to Krixil's deterministic mock provider — no API key configured, "
            "for local development."
        )

    return [ModelOut(id="auto", name="Krixil Auto", description=description)]


async def validate_model_id(model_id: str | None) -> None:
    if model_id is None:
        return
    catalog_ids = {m.id for m in await get_model_catalog()}
    if model_id not in catalog_ids:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail=f"Unknown model '{model_id}'."
        )
