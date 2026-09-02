# Ordered provider fallback

Krixil's native agent and chat now share an opt-in inference fallback chain.
No extra cloud provider is enabled unless explicitly listed by the operator.
Listing a provider permits sending the same task messages and tool results to it;
review privacy and billing before enabling it. API keys stay in server settings.

## Configuration

Set these in the AI service environment, not the CLI environment:

```dotenv
MODEL_PROVIDER=groq
MODEL_FALLBACK_PROVIDERS=openrouter,ollama
MODEL_FALLBACK_COOLDOWN_SECONDS=60
MODEL_FALLBACK_QUOTA_COOLDOWN_SECONDS=3600
```

Configure each provider's API key and default model separately (`GROQ_MODEL`,
`OPENROUTER_MODEL`, `OLLAMA_DEFAULT_MODEL`). Only choose models supporting custom
tool calling for agent use. For a free-only chain, select an explicitly free
OpenRouter model and keep Groq on its free plan; fallback does not enforce billing
limits or make paid model defaults free. Ollama models must already be installed.
No credentials or running deployment are changed by this implementation.
Restart the service after configuration changes. Empty fallback list preserves
the existing single-provider behavior. Missing keys/unknown providers fail clearly.
Mock is rejected in a multi-provider chain to avoid silently fabricating success.

## Behavior

- At each inference request, try the primary followed by configured backups.
- Fall back on HTTP 402, 429, 500, 502, 503, 504 and HTTPX network/timeouts.
- Respect `Retry-After` seconds/date, using at least the configured cooldown.
  Known quota error codes and 402 use the longer quota cooldown. When upstream
  provides no reset time, the cooldown is an estimate, not the actual daily reset.
- Skip cooling providers on subsequent calls; prefer the primary again after recovery.
- A primary model override is not sent to backups; they use their own defaults.
- Pass the same message history and tool schemas to backups. Only inference is
  retried: the agent loop, persisted steps, tool execution and permission engine
  are not restarted. This prevents retry machinery from replaying completed tools;
  it cannot guarantee a model will never propose a duplicate operation.
- A stream can switch before content is delivered, never after partial content.
- Authentication errors, bad arguments, missing models and context overflow are
  surfaced instead of trying unrelated providers. Context compaction is separate.
- Backend logs record cooldown/selected provider without payloads or credentials.
  Agent steps and non-streaming chat expose the actual successful provider/model.

## Boundaries

Cooldown state is per server process, shared across users of that deployment's
provider credentials; it is not coordinated across workers and resets on restart.
Concurrent requests already in flight may still reach a newly cooling provider.
There is no background infinite retry or automatic wakeup when every provider is
unavailable: chat returns 503; native runs fail with a clear reason and keep their
persisted steps. Don't rerun a partially completed task blindly.

Embeddings stay with the primary provider to preserve vector-space compatibility.
The Groq adapter delegates embeddings to `OLLAMA_EMBEDDING_MODEL`, like the
Anthropic/Hugging Face adapters; it does not call a Groq embedding endpoint.
RAG/embedding errors can therefore still stop a request before inference fallback.
This is not a runtime failover mechanism for remote Hermes: Hermes manages its own
model calls. It also does not provide a universal tool-schema compatibility shim.
Keep existing execution/step budgets and tool approvals enabled.
