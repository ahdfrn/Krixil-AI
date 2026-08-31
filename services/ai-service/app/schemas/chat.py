import uuid
from datetime import datetime

from pydantic import BaseModel, Field


class ChatRequest(BaseModel):
    message: str = Field(min_length=1, max_length=8000)
    conversation_id: uuid.UUID | None = None
    model: str | None = None


class MessageOut(BaseModel):
    id: uuid.UUID
    role: str
    content: str
    created_at: datetime

    model_config = {"from_attributes": True}


class CitationOut(BaseModel):
    document_id: uuid.UUID
    filename: str
    page: int | None
    chunk_index: int


class ToolCallOut(BaseModel):
    tool_name: str
    summary: str


class ChatResponse(BaseModel):
    conversation_id: uuid.UUID
    message: MessageOut
    model: str
    citations: list[CitationOut] = []
    tool_calls: list[ToolCallOut] = []


class ConversationOut(BaseModel):
    id: uuid.UUID
    title: str
    created_at: datetime

    model_config = {"from_attributes": True}


class ConversationDetailOut(ConversationOut):
    messages: list[MessageOut]


class ConversationRenameRequest(BaseModel):
    title: str = Field(min_length=1, max_length=255)
