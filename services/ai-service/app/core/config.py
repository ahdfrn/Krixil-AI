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

    # Anthropic's real Messages API — NOT OpenAI-compatible (no /chat/completions, system is a
    # top-level field rather than a message, tool results/tool_use are content blocks, auth is
    # x-api-key not Bearer), so this is its own provider (app/ai/anthropic_provider.py), not
    # CloudModelProvider pointed at a different base_url. Anthropic has no embeddings endpoint at
    # all — AnthropicModelProvider.embeddings() calls Ollama's directly instead (see that file),
    # so RAG/knowledge search keeps working even when MODEL_PROVIDER=anthropic.
    anthropic_api_key: str = ""
    anthropic_base_url: str = "https://api.anthropic.com/v1"
    anthropic_model: str = "claude-sonnet-5"
    anthropic_api_version: str = "2023-06-01"
    anthropic_max_tokens: int = 4096

    # A local Ollama instance, reached over its own OpenAI-compatible endpoint — same
    # CloudModelProvider class as "openai" above, just pointed elsewhere with its own config so
    # real OpenAI-cloud settings stay untouched. host.docker.internal is correct when the api
    # container talks to Ollama running natively on the Windows host; use localhost instead when
    # running the app directly (outside Docker).
    ollama_base_url: str = "http://host.docker.internal:11434/v1"
    ollama_default_model: str = "qwen2.5:7b"
    ollama_embedding_model: str = "nomic-embed-text"

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
    # Raised from 5 to match agent_max_steps — caught live: switching the default model to
    # llama3.1:8b (from qwen2.5:7b) made a real, measurable difference in whether the agent even
    # attempts multi-step self-correction (qwen2.5:7b almost never used more than 1 tool call;
    # llama3.1:8b genuinely retried after a wrong path, listed files, then wrote correctly — 6
    # calls deep) but it then ran out of budget one call short of actually running the file it had
    # just written. 5 was sized around the weaker model's behavior, not this one's.
    agent_max_tool_calls: int = 8
    agent_max_execution_seconds: int = 120

    # How many tool calls a single /chat or /chat/stream turn may make before it's forced to give
    # a final answer — smaller than agent_max_tool_calls on purpose, chat should stay
    # conversationally snappy rather than turn into a research loop (that's what Agents /
    # Deep Research mode is for).
    chat_max_tool_calls: int = 3

    # Cap on how many long-term-memory facts get injected into a single chat turn's context —
    # same role rag_top_k plays for RAG. See app/memory/long_term.py.
    memory_max_facts: int = 50

    # Tracing is opt-out (not opt-in): if no collector is reachable at otel_exporter_endpoint,
    # spans just fail to export in the background — harmless, and never blocks a request.
    otel_enabled: bool = True
    otel_exporter_endpoint: str = "http://localhost:4318/v1/traces"

    # Empty by default — the web.search tool (app/tools/web_tools.py) fails with a clear,
    # non-fabricated error when this is unset rather than pretending to search anything.
    tavily_api_key: str = ""

    # Autonomous fine-tuning (training/, a separate native-Windows project — see
    # docs/architecture/learning-and-memory.md Phase 3). 100 rows matches Unsloth's own
    # documented bare-minimum guidance for a dataset that won't just overfit.
    finetune_min_examples: int = 100
    finetune_check_interval_hours: int = 24
    finetune_min_message_chars: int = 20

    # Coding agent (app/workspace, app/tools/code_tools.py, services/sandbox-runner). Each
    # tenant's files live under workspace_root/{tenant_id}/ — a bind-mounted volume shared with
    # the sandbox-runner container so it can see the same files a run command touches. Command
    # execution itself never happens inside the api container; api only ever calls out to
    # sandbox-runner over HTTP, matching this app's other container-to-container calls.
    workspace_root: str = "/workspaces"
    sandbox_runner_url: str = "http://sandbox-runner:8001"
    code_execution_timeout_seconds: int = 30

    # Real host-folder access (services/host-runner, app/tools/host_tools.py) — a second,
    # separate, native-Windows service (not in Docker, same reason training/ isn't) giving the
    # agent unsandboxed read/write/execute access to a real folder on this machine. No approval,
    # no isolation, full network — see docs/architecture/coding-agent.md ("Real host-folder
    # access") before touching this. host_runner_url follows the same host.docker.internal
    # pattern already used to reach the natively-installed Ollama.
    host_runner_url: str = "http://host.docker.internal:8002"
    host_runner_timeout_seconds: int = 60

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
