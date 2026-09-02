import uuid
from datetime import datetime

from pydantic import BaseModel, Field


class MCPServerCreate(BaseModel):
    name: str = Field(min_length=1, max_length=100, pattern=r"^[a-zA-Z0-9_-]+$")
    command: str = Field(min_length=1, max_length=500)
    args: list[str] = Field(default_factory=list)
    env: dict[str, str] = Field(default_factory=dict)


class MCPServerOut(BaseModel):
    id: uuid.UUID
    name: str
    command: str
    args: list[str]
    env: dict[str, str]
    created_at: datetime

    model_config = {"from_attributes": True}


class MCPToolOut(BaseModel):
    name: str
    description: str
    input_schema: dict
