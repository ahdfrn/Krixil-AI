import uuid
from datetime import datetime

from pydantic import BaseModel, Field

from app.schemas.agent import AgentRunOut


class SwarmRunRequest(BaseModel):
    goal: str = Field(min_length=1, max_length=4000)
    model: str | None = None
    # Real upper bound on how many sub-tasks decomposition may produce — not a target it always
    # hits (decompose_goal, app/agents/swarm.py, asks for "up to" this many and honestly uses
    # however many the model actually returns, 2..max_subtasks).
    max_subtasks: int = Field(default=5, ge=2, le=8)


class SwarmRunOut(BaseModel):
    id: uuid.UUID
    goal: str
    status: str
    model_id: str | None
    subtask_count: int
    synthesis: str | None
    error_message: str | None
    created_at: datetime
    completed_at: datetime | None

    model_config = {"from_attributes": True}


class SwarmRunDetailOut(SwarmRunOut):
    # Real per-child status — each one the exact same AgentRunOut shape `GET /agents/{id}/status`
    # returns, not a separate "swarm child" representation.
    children: list[AgentRunOut]
