import time

from app.ai.base import ModelMessage
from app.evaluation.base import EvalCase, EvalOutcome, register_case

_LATENCY_THRESHOLD_MS = 3000
_MAX_EXPECTED_TOKENS = 200


async def _generate_latency_under_threshold(session, tenant_ctx, provider, storage) -> EvalOutcome:
    start = time.monotonic()
    await provider.generate(
        [ModelMessage(role="user", content="Summarize Krixil AI in one sentence.")]
    )
    elapsed_ms = (time.monotonic() - start) * 1000
    passed = elapsed_ms < _LATENCY_THRESHOLD_MS
    return EvalOutcome(
        passed=passed,
        details={"elapsed_ms": round(elapsed_ms, 1), "threshold_ms": _LATENCY_THRESHOLD_MS},
    )


register_case(
    EvalCase(
        name="latency.generate_under_threshold",
        category="latency",
        run=_generate_latency_under_threshold,
    )
)


async def _generate_stays_within_token_budget(
    session, tenant_ctx, provider, storage
) -> EvalOutcome:
    response = await provider.generate(
        [ModelMessage(role="user", content="Summarize Krixil AI in one sentence.")]
    )
    total_tokens = response.usage.get("prompt_tokens", 0) + response.usage.get(
        "completion_tokens", 0
    )
    passed = total_tokens <= _MAX_EXPECTED_TOKENS
    return EvalOutcome(
        passed=passed, details={"total_tokens": total_tokens, "budget": _MAX_EXPECTED_TOKENS}
    )


register_case(
    EvalCase(
        name="cost.generate_within_token_budget",
        category="cost",
        run=_generate_stays_within_token_budget,
    )
)
