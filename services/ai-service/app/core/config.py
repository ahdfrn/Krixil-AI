from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    # protected_namespaces=(): our `model_provider` field name is unrelated to pydantic's own
    # "model_" internals, but pydantic warns about it by default — this opts out of that check.
    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", extra="ignore", protected_namespaces=()
    )

    app_env: str = "development"
    app_name: str = "krixil-ai"
    log_level: str = "INFO"
    api_v1_prefix: str = "/api/v1"
    cors_origins: str = "http://localhost:3000"

    jwt_secret: str = "changeme-generate-a-real-secret"
    jwt_algorithm: str = "HS256"
    jwt_expire_minutes: int = 60

    postgres_host: str = "localhost"
    postgres_port: int = 5432
    postgres_db: str = "krixil"
    postgres_user: str = "krixil"
    postgres_password: str = "changeme"
    database_url: str = ""

    redis_url: str = "redis://localhost:6379/0"

    minio_endpoint: str = "localhost:9000"
    minio_access_key: str = "minioadmin"
    minio_secret_key: str = "changeme123"
    minio_bucket: str = "krixil-documents"

    model_provider: str = "mock"
    openai_api_key: str = ""
    # OpenAI-compatible: works against api.openai.com or any compatible endpoint (self-hosted
    # vLLM, OpenRouter, etc.) by overriding base_url — the provider code has no vendor-specific
    # logic.
    openai_base_url: str = "https://api.openai.com/v1"
    openai_model: str = "gpt-4o-mini"
    openai_embedding_model: str = "text-embedding-3-small"

    short_term_memory_max_messages: int = 20
    short_term_memory_ttl_seconds: int = 60 * 60 * 24  # 24h — this is short-term cache, not history

    rate_limit_chat_per_minute: int = 30

    # 1536 matches OpenAI's text-embedding-3-small (the default OPENAI_EMBEDDING_MODEL) so the
    # real-provider path needs no config change out of the box. MockProvider reads this too and
    # produces vectors of this size, so MODEL_PROVIDER=mock (the default) also just works —
    # switching *away* from the default embedding model is what requires updating this to match.
    embedding_dimension: int = 1536
    rag_chunk_size: int = 1000
    rag_chunk_overlap: int = 150
    rag_top_k: int = 5
    max_document_size_mb: int = 20

    # Budgets an agent run stops itself at — not client-configurable in Phase 4 (kept simple);
    # per-run overrides are a natural, self-contained addition later if needed.
    agent_max_steps: int = 8
    agent_max_tool_calls: int = 5
    agent_max_execution_seconds: int = 120

    # Tracing is opt-out (not opt-in): if no collector is reachable at otel_exporter_endpoint,
    # spans just fail to export in the background — harmless, and never blocks a request.
    otel_enabled: bool = True
    otel_exporter_endpoint: str = "http://localhost:4318/v1/traces"

    @property
    def sqlalchemy_database_url(self) -> str:
        if self.database_url:
            return self.database_url
        return (
            f"postgresql+asyncpg://{self.postgres_user}:{self.postgres_password}"
            f"@{self.postgres_host}:{self.postgres_port}/{self.postgres_db}"
        )

    @property
    def cors_origins_list(self) -> list[str]:
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]

    @property
    def is_production(self) -> bool:
        return self.app_env == "production"


@lru_cache
def get_settings() -> Settings:
    return Settings()
