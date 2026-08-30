import uuid
from datetime import datetime

from pydantic import BaseModel


class ToolOut(BaseModel):
    name: str
    description: str
    risk_level: str
    required_permission: str
    input_schema: dict


class ToolExecutionOut(BaseModel):
    id: uuid.UUID
    tool_name: str
    risk_level: str
    status: str
    input: dict
    output: dict | None
    error_message: str | None
    created_at: datetime
    completed_at: datetime | None

    model_config = {"from_attributes": True}


class RejectExecutionRequest(BaseModel):
    reason: str | None = None
