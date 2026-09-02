"""Small manual smoke test. Never prints keys or upstream error bodies; executes no tools."""

import asyncio
import sys
from pathlib import Path

import httpx

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.ai.base import ModelMessage, ToolSchema
from app.ai.router import ModelRouter, aclose_providers


async def main():
    router = ModelRouter()
    try:
        for name in (sys.argv[1:] or ["groq", "openrouter"]):
            provider = router._get_named_provider(name)
            messages = [ModelMessage("system", "Reply briefly in Indonesian. Do not invent context."),
                        ModelMessage("user", "halo")]
            for operation in ("chat", "tool_call"):
                try:
                    if operation == "chat":
                        result = await provider.generate(messages, max_tokens=2048)
                        print(name, operation, "OK", result.model,
                              "nonempty_answer=" + str(bool(result.content.strip())), flush=True)
                    else:
                        result = await provider.tool_call(
                            [ModelMessage("user", "Call check_status with target demo. This is a test.")],
                            [ToolSchema("check_status", "Check a named test target", {
                                "type": "object", "properties": {"target": {"type": "string"}},
                                "required": ["target"], "additionalProperties": False,
                            })], max_tokens=512,
                        )
                        valid = any(call.name == "check_status" and call.arguments == {"target": "demo"}
                                    for call in result.tool_calls)
                        print(name, operation, "VALID" if valid else "NO_VALID_CALL",
                              "(not executed)", flush=True)
                except httpx.HTTPStatusError as error:
                    print(name, operation, "HTTP", error.response.status_code, flush=True)
                except Exception as error:
                    print(name, operation, type(error).__name__, flush=True)
    finally:
        await aclose_providers()


asyncio.run(main())
