from app.ai.base import ModelMessage, ToolSchema
from app.ai.mock_provider import MockProvider

KNOWLEDGE_TOOL = ToolSchema(
    name="knowledge.search",
    description="Search docs",
    parameters={
        "type": "object",
        "properties": {"query": {"type": "string"}},
        "required": ["query"],
    },
)
DOCUMENT_DELETE_TOOL = ToolSchema(
    name="document.delete",
    description="Delete a document",
    parameters={
        "type": "object",
        "properties": {"document_id": {"type": "string", "format": "uuid"}},
        "required": ["document_id"],
    },
)
USAGE_TOOL = ToolSchema(
    name="usage.get_summary",
    description="Usage summary",
    parameters={"type": "object", "properties": {"days": {"type": "integer"}}, "required": []},
)


async def test_tool_call_matches_tool_by_name_keyword_and_fills_required_string():
    provider = MockProvider()
    messages = [ModelMessage(role="user", content="please search the knowledge base for pgvector")]

    response = await provider.tool_call(messages, [KNOWLEDGE_TOOL])

    assert len(response.tool_calls) == 1
    assert response.tool_calls[0].name == "knowledge.search"
    assert response.tool_calls[0].arguments["query"] == messages[0].content


async def test_tool_call_extracts_uuid_for_required_uuid_field():
    provider = MockProvider()
    document_id = "12345678-1234-1234-1234-123456789abc"
    messages = [ModelMessage(role="user", content=f"please delete document {document_id}")]

    response = await provider.tool_call(messages, [DOCUMENT_DELETE_TOOL])

    assert response.tool_calls[0].name == "document.delete"
    assert response.tool_calls[0].arguments["document_id"] == document_id


async def test_tool_call_with_no_required_fields_returns_empty_arguments():
    provider = MockProvider()
    messages = [ModelMessage(role="user", content="give me a usage summary please")]

    response = await provider.tool_call(messages, [USAGE_TOOL])

    assert response.tool_calls[0].name == "usage.get_summary"
    assert response.tool_calls[0].arguments == {}


async def test_tool_call_with_no_matching_keyword_returns_final_answer():
    provider = MockProvider()
    messages = [ModelMessage(role="user", content="what's the weather like today?")]

    response = await provider.tool_call(
        messages, [KNOWLEDGE_TOOL, DOCUMENT_DELETE_TOOL, USAGE_TOOL]
    )

    assert response.tool_calls == []
    assert "weather" in response.content
