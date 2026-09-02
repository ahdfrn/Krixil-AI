import json
from collections.abc import AsyncIterator

import app.ai.router as router_module
from app.agents.swarm import _parse_subtasks
from app.ai.base import ModelMessage, ModelProvider, ModelResponse, ToolSchema
from tests.helpers import auth_headers, register


def _subtask(goal: str, depends_on: list[int] | None = None) -> dict:
    return {"goal": goal, "depends_on": depends_on or []}


def test_parse_subtasks_from_a_clean_json_array():
    raw = json.dumps(
        [_subtask("Security audit"), _subtask("Database audit"), _subtask("Frontend audit")]
    )
    assert _parse_subtasks(raw, max_subtasks=5) == [
        ("Security audit", []),
        ("Database audit", []),
        ("Frontend audit", []),
    ]


def test_parse_subtasks_strips_a_markdown_code_fence():
    payload = json.dumps([_subtask("Security audit"), _subtask("Database audit")])
    raw = f"```json\n{payload}\n```"
    assert _parse_subtasks(raw, max_subtasks=5) == [
        ("Security audit", []),
        ("Database audit", []),
    ]


def test_parse_subtasks_truncates_to_max_subtasks():
    raw = json.dumps([_subtask(x) for x in "abcde"])
    assert _parse_subtasks(raw, max_subtasks=3) == [("a", []), ("b", []), ("c", [])]


def test_parse_subtasks_returns_empty_for_invalid_json():
    assert _parse_subtasks("not json at all", max_subtasks=5) == []


def test_parse_subtasks_returns_empty_for_a_non_array():
    assert _parse_subtasks(json.dumps({"not": "an array"}), max_subtasks=5) == []


def test_parse_subtasks_returns_empty_for_blank_or_malformed_entries():
    raw = json.dumps([_subtask("Security audit"), {"goal": "  "}, _subtask("Database audit")])
    assert _parse_subtasks(raw, max_subtasks=5) == []


def test_parse_subtasks_returns_empty_for_a_non_dict_item():
    raw = json.dumps([_subtask("Security audit"), "just a string"])
    assert _parse_subtasks(raw, max_subtasks=5) == []


def test_parse_subtasks_accepts_a_valid_diamond_shaped_dependency_graph():
    # Matches the PRD §27 diagram: Backend/Frontend/Database run independently, Testing depends
    # on all three, Security depends on Testing.
    raw = json.dumps(
        [
            _subtask("Backend"),
            _subtask("Frontend"),
            _subtask("Database"),
            _subtask("Testing", [0, 1, 2]),
            _subtask("Security", [3]),
        ]
    )
    assert _parse_subtasks(raw, max_subtasks=8) == [
        ("Backend", []),
        ("Frontend", []),
        ("Database", []),
        ("Testing", [0, 1, 2]),
        ("Security", [3]),
    ]


def test_parse_subtasks_rejects_a_self_reference():
    raw = json.dumps([_subtask("a"), _subtask("b", [1])])
    assert _parse_subtasks(raw, max_subtasks=5) == []


def test_parse_subtasks_rejects_a_dangling_reference():
    raw = json.dumps([_subtask("a"), _subtask("b", [5])])
    assert _parse_subtasks(raw, max_subtasks=5) == []


def test_parse_subtasks_rejects_a_cycle():
    raw = json.dumps([_subtask("a", [1]), _subtask("b", [0])])
    assert _parse_subtasks(raw, max_subtasks=5) == []


def test_parse_subtasks_rejects_a_reference_invalidated_by_truncation():
    # 6 items with max_subtasks=5 — item 5 (truncated away) was item 4's only dependency target,
    # which must correctly fail the whole decomposition, not silently drop the broken edge.
    raw = json.dumps([_subtask(x) for x in "abcd"] + [_subtask("e", [5]), _subtask("f")])
    assert _parse_subtasks(raw, max_subtasks=5) == []


class _SwarmTestProvider(ModelProvider):
    """A real, deterministic ModelProvider that returns a real JSON sub-task array for the
    decomposition prompt specifically, and a real short "done" answer for every child's own
    tool_call — MockProvider can't stand in for decomposition since it never produces JSON at
    all, which is exactly the *honest-failure* path (see
    test_swarm_run_fails_honestly_when_decomposition_produces_no_json below) rather than the
    happy path this class exists to exercise."""

    name = "mock"

    def __init__(self, subtasks: list[dict], fail_on_substring: str | None = None):
        self._subtasks = subtasks
        # If set, tool_call() raises for any child whose prompt contains this substring — used to
        # exercise the real "prerequisite failed" path without needing new production code.
        self._fail_on_substring = fail_on_substring

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
        # The "not in last_user" check matters: a dependent child's own injected prompt embeds
        # its prerequisite's real goal text too (see _inject_dependency_context), so a bare
        # substring match would wrongly also trip on the dependent itself, not just the leaf
        # sub-task this is meant to fail.
        if (
            self._fail_on_substring
            and self._fail_on_substring in last_user
            and "Context from prerequisite" not in last_user
        ):
            raise RuntimeError("boom — this sub-task deliberately fails, on purpose")
        return ModelResponse(content=f"Done: {last_user[:80]}", model=self.name)

    async def health_check(self) -> bool:  # pragma: no cover
        return True


async def test_swarm_run_decomposes_and_completes_children_in_parallel(client, monkeypatch):
    subtasks = [
        _subtask("Security audit of the codebase"),
        _subtask("Database schema audit"),
        _subtask("Frontend a11y audit"),
    ]
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
        assert {c["goal"] for c in children} == {s["goal"] for s in subtasks}
        assert all(c["status"] == "completed" for c in children)
        assert all(c["swarm_run_id"] == swarm_id for c in children)
        assert all(c["final_response"] for c in children)
        assert all(c["depends_on"] == [] for c in children)
        assert all(c["original_goal"] is None for c in children)
    finally:
        router_module._instances.pop("mock", None)


async def test_swarm_dependent_child_prompt_includes_prerequisite_output(client):
    subtasks = [
        _subtask("Build the backend API"),
        _subtask("Build the frontend UI"),
        _subtask("Write integration tests covering backend and frontend", [0, 1]),
    ]
    router_module._instances["mock"] = _SwarmTestProvider(subtasks)

    registered = await register(client)
    headers = auth_headers(registered["access_token"])

    try:
        run_resp = await client.post(
            "/api/v1/agents/swarm", json={"goal": "build and test a small app"}, headers=headers
        )
        swarm_id = run_resp.json()["id"]

        status_resp = await client.get(f"/api/v1/agents/swarm/{swarm_id}/status", headers=headers)
        body = status_resp.json()
        assert body["status"] == "completed"

        children = body["children"]
        dependent = next(c for c in children if c["depends_on"])
        assert len(dependent["depends_on"]) == 2
        assert dependent["original_goal"] == "Write integration tests covering backend and frontend"
        assert "Context from prerequisite sub-task(s)" in dependent["goal"]
        # _SwarmTestProvider.tool_call() echoes back f"Done: {prompt[:80]}" — finding that real
        # completed text embedded in the dependent's own goal is direct proof of real data flow,
        # not a timing coincidence.
        assert "Done: Build the backend API" in dependent["goal"]
        assert "Done: Build the frontend UI" in dependent["goal"]
        assert dependent["status"] == "completed"
    finally:
        router_module._instances.pop("mock", None)


async def test_swarm_dependent_child_still_runs_after_a_failed_prerequisite(client):
    subtasks = [
        _subtask("Build the backend API"),
        _subtask("Build the frontend UI"),
        _subtask("Write integration tests covering backend and frontend", [0, 1]),
    ]
    router_module._instances["mock"] = _SwarmTestProvider(
        subtasks, fail_on_substring="Build the frontend UI"
    )

    registered = await register(client)
    headers = auth_headers(registered["access_token"])

    try:
        run_resp = await client.post(
            "/api/v1/agents/swarm", json={"goal": "build and test a small app"}, headers=headers
        )
        swarm_id = run_resp.json()["id"]

        status_resp = await client.get(f"/api/v1/agents/swarm/{swarm_id}/status", headers=headers)
        body = status_resp.json()

        children = body["children"]
        failed_sibling = next(c for c in children if c["goal"] == "Build the frontend UI")
        assert failed_sibling["status"] == "failed"

        dependent = next(c for c in children if c["depends_on"])
        # The dependent still ran — honest hand-off, not a silent skip — with the real failure
        # note and the failed sibling's real error text injected into its own goal/prompt.
        assert dependent["status"] == "completed"
        assert "did not complete successfully" in dependent["goal"]
        assert "Done: Build the backend API" in dependent["goal"]
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
