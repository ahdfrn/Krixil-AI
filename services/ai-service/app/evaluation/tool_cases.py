from app.ai.base import ModelMessage, ToolSchema
from app.evaluation.base import EvalCase, EvalOutcome, register_case
from app.tools.base import list_tools


def _tool_schemas() -> list[ToolSchema]:
    return [
        ToolSchema(
            name=t.name, description=t.description, parameters=t.input_model.model_json_schema()
        )
        for t in list_tools()
    ]


async def _model_selects_correct_tool(session, tenant_ctx, provider, storage) -> EvalOutcome:
    messages = [ModelMessage(role="user", content="please give me a usage summary")]
    response = await provider.tool_call(messages, _tool_schemas())
    selected = response.tool_calls[0].name if response.tool_calls else None
    passed = selected == "usage.get_summary"
    return EvalOutcome(passed=passed, details={"selected_tool": selected})


register_case(
    EvalCase(
        name="tool_calling.selects_usage_summary_tool",
        category="tool_calling",
        run=_model_selects_correct_tool,
    )
)
