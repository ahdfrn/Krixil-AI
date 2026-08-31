import uuid
from datetime import datetime

from pydantic import BaseModel, Field


class FinetuneDatasetOut(BaseModel):
    example_count: int
    rows: list[dict]


class FinetuneRunOut(BaseModel):
    id: uuid.UUID
    status: str
    example_count: int
    candidate_tag: str | None
    promoted_tag: str | None
    eval_pass_count: int | None
    eval_fail_count: int | None
    regression: bool | None
    detail: str | None
    created_at: datetime
    completed_at: datetime | None

    model_config = {"from_attributes": True}


class FinetuneStatusOut(BaseModel):
    example_count: int
    min_examples: int
    ready: bool
    runs: list[FinetuneRunOut]


class FinetuneStartRunRequest(BaseModel):
    example_count: int = Field(ge=0)


class FinetuneEvaluateRequest(BaseModel):
    model_tag: str = Field(min_length=1, max_length=255)


class FinetuneEvaluateOut(BaseModel):
    pass_count: int
    fail_count: int
    regression: bool | None


class FinetuneReportRequest(BaseModel):
    run_id: uuid.UUID
    status: str = Field(pattern="^(promoted|discarded|failed)$")
    candidate_tag: str | None = None
    promoted_tag: str | None = None
    eval_pass_count: int | None = None
    eval_fail_count: int | None = None
    regression: bool | None = None
    detail: str | None = None
