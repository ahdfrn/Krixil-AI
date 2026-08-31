import json

from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.base import ModelMessage, ModelProvider, ToolSchema
from app.core.config import get_settings
from app.schemas.chat import ToolCallOut
from app.tenancy.context import TenantContext
from app.tools.base import RiskLevel, list_tools
from app.tools.service import request_tool_execution

# Human-readable labels for the tool-call UI (components/chat/tool-call-display.tsx) — plain
# language, never a raw tool name. Local to this module since it's a presentation detail specific
# to this one caller, not part of the Tool definition itself.
_DISPLAY_LABELS = {
    "knowledge.search": "Searched your knowledge base",
    "usage.get_summary": "Checked your usage summary",
    "web.search": "Searched the web",
    "code.list_files": "Looked at your coding workspace",
    "code.read_file": "Read a file from your coding workspace",
}


async def run_chat_tools(
    session: AsyncSession,
    tenant_ctx: TenantContext,
    provider: ModelProvider,
    model_messages: list[ModelMessage],
    *,
    model_id: str | None = None,
) -> list[ToolCallOut]:
    """Lets a chat turn call a small, safe set of tools inline before the final answer is
    generated — same message-augmentation loop app/agents/runner.py uses, but bounded to
    chat_max_tool_calls and restricted to LOW-risk tools only. Chat resolves tool calls with no
    human-approval step, so the model is never even offered a tool that could land in
    pending_approval; that stays Agents/Tools-page territory. Mutates model_messages in place with
    the tool-call/result turns and returns [{"tool_name", "summary"}, ...] for whatever was
    actually invoked, for the frontend's tool-call UI. model_id (a ChatRequest.model value) is
    forwarded to the provider so tool-calling honors the same per-request model selection the
    final answer uses — "auto"/None mean "use the provider's own default".
    """
    allowed_tools = [t for t in list_tools() if t.risk_level == RiskLevel.LOW]
    if not allowed_tools:
        return []
    tool_schemas = [
        ToolSchema(
            name=t.name, description=t.description, parameters=t.input_model.model_json_schema()
        )
        for t in allowed_tools
    ]
    model_kwargs = {} if model_id is None or model_id == "auto" else {"model": model_id}

    invoked: list[ToolCallOut] = []
    for _ in range(get_settings().chat_max_tool_calls):
        response = await provider.tool_call(model_messages, tool_schemas, **model_kwargs)
        if not response.tool_calls:
            break

        call = response.tool_calls[0]
        try:
            execution = await request_tool_execution(session, tenant_ctx, call.name, call.arguments)
        except HTTPException as exc:
            observation = {"error": str(exc.detail)}
        else:
            if execution.status == "completed" and execution.output is not None:
                observation = execution.output
                invoked.append(
                    ToolCallOut(
                        tool_name=call.name,
                        summary=_DISPLAY_LABELS.get(call.name, f"Used {call.name}"),
                    )
                )
            else:
                observation = {"error": execution.error_message or "unknown error"}

        model_messages.append(ModelMessage(role="assistant", content=f"Called tool {call.name}."))
        model_messages.append(
            ModelMessage(role="user", content=f"Tool result: {json.dumps(observation)}")
        )

    return invoked
