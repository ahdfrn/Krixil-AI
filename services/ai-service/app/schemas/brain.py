import uuid
from datetime import datetime

from pydantic import BaseModel, Field


class BrainIndexRequest(BaseModel):
    # Same convention as HostRunCommandInput.directory (app/tools/host_tools.py) — relative to
    # HOST_ROOT, "." meaning the whole tree.
    directory: str = Field(default=".", max_length=1000)


class BrainIndexRunOut(BaseModel):
    id: uuid.UUID
    directory: str
    status: str
    file_count: int
    symbol_count: int
    chunk_count: int
    error_message: str | None
    created_at: datetime
    completed_at: datetime | None

    model_config = {"from_attributes": True}


class BrainSearchRequest(BaseModel):
    query: str = Field(min_length=1, max_length=1000)
    limit: int = Field(default=10, ge=1, le=50)


class BrainSearchResultOut(BaseModel):
    path: str
    language: str | None
    content: str
