import json
from collections.abc import AsyncIterator

import app.ai.router as router_module
from app.agents.swarm import _parse_subtasks
from app.ai.base import ModelMessage, ModelProvider, ModelResponse, ToolSchema
from tests.helpers import auth_headers, register


def test_parse_subtasks_from_a_clean_json_array():
    raw = json.dumps(["Security audit", "Database audit", "Frontend audit"])
    assert _parse_subtasks(raw, max_subtasks=5) == [
        "Security audit",
        "Database audit",
        "Frontend audit",
    ]


def test_parse_subtasks_strips_a_markdown_code_fence():
    raw = '```json\n["Security audit", "Database audit"]\n```'
    assert _parse_subtasks(raw, max_subtasks=5) == ["Security audit", "Database audit"]


def test_parse_subtasks_truncates_to_max_subtasks():
    raw = json.dumps(["a", "b", "c", "d", "e"])
    assert _parse_subtasks(raw, max_subtasks=3) == ["a", "b", "c"]


def test_parse_subtasks_returns_empty_for_invalid_json():
    assert _parse_subtasks("not json at all", max_subtasks=5) == []


def test_parse_subtasks_returns_empty_for_a_non_array():
    assert _parse_subtasks(json.dumps({"not": "an array"}), max_subtasks=5) == []


def test_parse_subtasks_drops_blank_entries():
    raw = json.dumps(["Security audit", "  ", "", "Database audit"])
    assert _parse_subtasks(raw, max_subtasks=5) == ["Security audit", "Database audit"]


class _SwarmTestProvider(ModelProvider):
    """A real, deterministic ModelProvider that returns a real JSON sub-task array for the
    decomposition prompt specifically, and a real short "done" answer for every child's own
    tool_call — MockProvider can't stand in for decomposition since it never produces JSON at
    all, which is exactly the *honest-failure* path (see
    test_swarm_run_fails_honestly_when_decomposition_produces_no_json below) rather than the
    happy path this class exists to exercise."""

    name = "mock"

    def __init__(self, subtasks: list[str]):
        self._subtasks = subtasks

    async def generate(self, messages: list[ModelMessage], **kwargs) -> ModelResponse:
        system = messages[0].content if messages and messages[0].role == "system" else ""
        if "Break the following goal" in system:
            return ModelResponse(content=json.dumps(self._subtasks), model=self.name)
        # The synthesis call — a real, short, honestly-labeled text, not fabricated JSON.
        last_user = messages[-1].content if messages else ""
        return ModelResponse(content=f"Synthesis covering: {last_user[:80]}", model=self.name)

    def stream(
        self, messages: list[ModelMessage], **kwargs
    ) -> AsyncIterator[str]:  # pragma: no cover
        raise NotImplementedError

    async def embeddings(self, texts: list[str]) -> list[list[float]]:  # pragma: no cover
        raise NotImplementedError

    async def tool_call(
        self, messages: list[ModelMessage], tools: list[ToolSchema], **kwargs
    ) -> ModelResponse:
        # Every child completes in one step with no tool calls — same shape MockProvider itself
        # falls back to when nothing matches a real tool name.
        last_user = messages[-1].content if messages else ""
        return ModelResponse(content=f"Done: {last_user[:80]}", model=self.name)

    async def health_check(self) -> bool:  # pragma: no cover
        return True


async def test_swarm_run_decomposes_and_completes_children_in_parallel(client, monkeypatch):
    subtasks = ["Security audit of the codebase", "Database schema audit", "Frontend a11y audit"]
    fake_provider = _SwarmTestProvider(subtasks)
    router_module._instances["mock"] = fake_provider

    registered = await register(client)
    headers = auth_headers(registered["access_token"])

    try:
        run_resp = await client.post(
            "/api/v1/agents/swarm",
            json={"goal": "make this application production ready"},
            headers=headers,
        )
        assert run_resp.status_code == 200
        swarm_id = run_resp.json()["id"]

        # Background tasks run to completion before the POST above returns (same Starlette
        # TestClient behavior every other background-task test in this suite relies on) — this
        # GET reflects the real final state already, no poll/sleep needed.
        status_resp = await client.get(f"/api/v1/agents/swarm/{swarm_id}/status", headers=headers)
        body = status_resp.json()

        assert body["status"] == "completed"
        assert body["subtask_count"] == 3
        assert body["synthesis"]
        assert "Synthesis covering" in body["synthesis"]

        children = body["children"]
        assert len(children) == 3
        assert {c["goal"] for c in children} == set(subtasks)
        assert all(c["status"] == "completed" for c in children)
        assert all(c["swarm_run_id"] == swarm_id for c in children)
        assert all(c["final_response"] for c in children)
    finally:
        router_module._instances.pop("mock", None)


async def test_swarm_run_fails_honestly_when_decomposition_produces_no_json(client):
    """The real, unmodified MockProvider (app/ai/mock_provider.py) never produces JSON from
    generate() — it just echoes the prompt back. This is the real, honest failure path: no
    fabricated sub-tasks, no silently running the original goal as a lone "swarm" of one."""
    registered = await register(client)
    headers = auth_headers(registered["access_token"])

    run_resp = await client.post(
        "/api/v1/agents/swarm", json={"goal": "do something"}, headers=headers
    )
    swarm_id = run_resp.json()["id"]

    status_resp = await client.get(f"/api/v1/agents/swarm/{swarm_id}/status", headers=headers)
    body = status_resp.json()

    assert body["status"] == "failed"
    assert "Couldn't decompose" in body["error_message"]
    assert body["subtask_count"] == 0
    assert body["children"] == []


async def test_swarm_runs_are_tenant_scoped(client):
    tenant_a = await register(client, tenant_name="Swarm Tenant A", email="a@swarm.dev")
    tenant_b = await register(client, tenant_name="Swarm Tenant B", email="b@swarm.dev")
    headers_a = auth_headers(tenant_a["access_token"])
    headers_b = auth_headers(tenant_b["access_token"])

    run_resp = await client.post("/api/v1/agents/swarm", json={"goal": "hello"}, headers=headers_a)
    swarm_id = run_resp.json()["id"]

    status_resp = await client.get(f"/api/v1/agents/swarm/{swarm_id}/status", headers=headers_b)
    assert status_resp.status_code == 404

    list_resp = await client.get("/api/v1/agents/swarm", headers=headers_b)
    assert list_resp.json() == []
