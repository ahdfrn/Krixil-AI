"""Custom metrics beyond what prometheus-fastapi-instrumentator already gives for free (HTTP
request count/duration/in-progress by method+path+status). These use the same default
prometheus_client registry, so they show up on the same /metrics endpoint automatically."""

from prometheus_client import Counter, Histogram

MODEL_REQUEST_DURATION = Histogram(
    "krixil_model_request_duration_seconds",
    "Model provider call duration",
    ["provider", "operation"],
)

TOKEN_USAGE = Counter(
    "krixil_token_usage_total",
    "Tokens consumed",
    ["model", "token_type"],
)

TOOL_EXECUTION_DURATION = Histogram(
    "krixil_tool_execution_duration_seconds",
    "Tool execution duration",
    ["tool_name", "status"],
)

RAG_SEARCH_DURATION = Histogram(
    "krixil_rag_search_duration_seconds",
    "Hybrid search (vector + keyword) duration",
)

AGENT_STEPS = Counter(
    "krixil_agent_steps_total",
    "Agent loop steps executed",
    ["step_type"],
)

SHORT_TERM_MEMORY_CACHE = Counter(
    "krixil_short_term_memory_cache_total",
    "Short-term memory (Redis) cache lookups",
    ["result"],  # "hit" | "miss"
)
