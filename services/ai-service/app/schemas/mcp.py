import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field, model_validator


class MCPServerCreate(BaseModel):
    name: str = Field(min_length=1, max_length=100, pattern=r"^[a-zA-Z0-9_-]+$")
    transport: Literal["stdio", "sse", "http"] = "stdio"
    command: str | None = Field(default=None, max_length=500)
    args: list[str] = Field(default_factory=list)
    env: dict[str, str] = Field(default_factory=dict)
    url: str | None = Field(default=None, max_length=2000)
    headers: dict[str, str] = Field(default_factory=dict)

    @model_validator(mode="after")
    def _validate_transport_fields(self) -> "MCPServerCreate":
        if self.transport == "stdio":
            if not self.command or not self.command.strip():
                raise ValueError('`command` is required for transport="stdio".')
            if self.url or self.headers:
                raise ValueError('`url`/`headers` are only valid for transport="sse"/"http".')
        else:
            if not self.url or not self.url.strip():
                raise ValueError(f'`url` is required for transport="{self.transport}".')
            if not self.url.startswith(("http://", "https://")):
                raise ValueError('`url` must start with "http://" or "https://".')
            if self.command or self.args or self.env:
                raise ValueError(
                    f'`command`/`args`/`env` are only valid for transport="stdio", '
                    f'not "{self.transport}".'
                )
        return self


class MCPServerOut(BaseModel):
    id: uuid.UUID
    name: str
    transport: str
    command: str | None
    args: list[str]
    env: dict[str, str]
    url: str | None
    headers: dict[str, str]
    created_at: datetime

    model_config = {"from_attributes": True}


class MCPToolOut(BaseModel):
    name: str
    description: str
    input_schema: dict
