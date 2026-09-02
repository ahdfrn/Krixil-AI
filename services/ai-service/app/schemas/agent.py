import uuid
from datetime import datetime

from pydantic import BaseModel, Field


class AgentRunRequest(BaseModel):
    goal: str = Field(min_length=1, max_length=4000)
    # "auto"/None both mean the provider's own configured default — same convention as
    # ChatRequest.model (app/schemas/chat.py). Persisted on AgentRun (model_id) so a run that
    # pauses for approval can resume on the same model.
    model: str | None = None
    # PRD §34's `agent.max_iterations` (cli/src/projectConfig.ts). None means "use the
    # deployment's own configured ceiling" (settings.agent_max_steps) — when given, only ever
    # *tightens* that ceiling (see create_agent_run), never raises it, so a client-supplied value
    # can't become a way to exceed the operator's own configured resource limit.
    max_steps: int | None = Field(default=None, gt=0)


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
    model_id: str | None
    # Set only when this run is one real child of a Multi-Agent Swarm (app/agents/swarm.py) —
    # None for every ordinary run.
    swarm_run_id: uuid.UUID | None
    created_at: datetime
    completed_at: datetime | None

    model_config = {"from_attributes": True}


class AgentRunDetailOut(AgentRunOut):
    steps: list[AgentStepOut]
