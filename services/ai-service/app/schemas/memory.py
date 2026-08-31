import uuid
from datetime import datetime

from pydantic import BaseModel, Field


class MemoryOut(BaseModel):
    id: uuid.UUID
    content: str
    created_at: datetime

    model_config = {"from_attributes": True}


class MemoryCreateRequest(BaseModel):
    content: str = Field(min_length=1, max_length=2000)


class MemorySettingsOut(BaseModel):
    memory_enabled: bool


class MemorySettingsUpdateRequest(BaseModel):
    enabled: bool
