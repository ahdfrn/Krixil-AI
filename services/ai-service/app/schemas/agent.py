import uuid
from datetime import datetime

from pydantic import BaseModel, Field


class AgentRunRequest(BaseModel):
    goal: str = Field(min_length=1, max_length=4000)


class AgentStepOut(BaseModel):
    step_number: int
    type: str
    tool_name: str | None
    content: dict
    created_at: datetime

    model_config = {"from_attributes": True}


class AgentRunOut(BaseModel):
    id: uuid.UUID
    goal: str
    status: str
    step_count: int
    tool_call_count: int
    max_steps: int
    max_tool_calls: int
    final_response: str | None
    error_message: str | None
    pending_execution_id: uuid.UUID | None
    created_at: datetime
    completed_at: datetime | None

    model_config = {"from_attributes": True}


class AgentRunDetailOut(AgentRunOut):
    steps: list[AgentStepOut]
