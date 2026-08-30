from fastapi import HTTPException, status

from app.core.config import Settings, get_settings
from app.schemas.model import ModelOut


def get_model_catalog(settings: Settings | None = None) -> list[ModelOut]:
    """Today there is exactly one real, selectable model: whichever provider MODEL_PROVIDER
    resolves to. ModelRouter (app/ai/router.py) has no concept of multiple simultaneously
    available models yet — this is deliberately the one place a second real entry gets added
    later, not a catalog of fabricated named variants."""
    settings = settings or get_settings()

    if settings.model_provider == "openai":
        description = (
            f"Routes to {settings.openai_model} via the configured OpenAI-compatible endpoint."
        )
    else:
        description = (
            "Routes to Krixil's deterministic mock provider — no API key configured, "
            "for local development."
        )

    return [ModelOut(id="auto", name="Krixil Auto", description=description)]


def validate_model_id(model_id: str | None) -> None:
    if model_id is None:
        return
    catalog_ids = {m.id for m in get_model_catalog()}
    if model_id not in catalog_ids:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail=f"Unknown model '{model_id}'."
        )
