import uuid

from app.agents.runner import run_agent
from app.agents.service import create_agent_run
from app.ai.router import ModelRouter
from app.core.config import get_settings
from app.tenancy.context import TenantContext
from tests.helpers import auth_headers, register


async def test_agent_completes_without_calling_a_tool(client):
    registered = await register(client)
    headers = auth_headers(registered["access_token"])

    resp = await client.post(
        "/api/v1/agents/run", json={"goal": "what's the weather like today?"}, headers=headers
    )
    assert resp.status_code == 200
    run_id = resp.json()["id"]

    # POST /agents/run now returns the instant the run row is created — the loop itself runs in a
    # background task (see app/agents/router.py) so the Code page can poll and show steps live
    # instead of blocking for up to max_execution_seconds. In tests, background tasks still run to
    # completion before `await client.post(...)` returns (standard FastAPI/Starlette/httpx
    # behavior), so a single follow-up status fetch — no sleep/retry needed — already reflects the
    # final state.
    status_resp = await client.get(f"/api/v1/agents/{run_id}/status", headers=headers)
    body = status_resp.json()
    assert body["status"] == "completed"
    assert body["tool_call_count"] == 0
    assert body["final_response"]


async def test_completed_agent_run_feeds_the_same_learning_pipeline_as_chat(client):
    """A completed run (real final_response) is fed to extract_and_store_memories exactly like a
    chat turn (app/agents/router.py) — MockProvider.generate() just echoes "Mock response to:
    <prompt>" for the extraction call too, not the {"memories": [...], "notes": [...]} JSON
    extraction expects, so this only proves the wiring doesn't crash and degrades gracefully to
    no rows — same limitation test_memory.py's equivalent chat test already accepts; there's no
    positive-extraction test for chat either to be consistent with."""
    registered = await register(client)
    headers = auth_headers(registered["access_token"])

    resp = await client.post(
        "/api/v1/agents/run", json={"goal": "what's the weather like today?"}, headers=headers
    )
    assert resp.status_code == 200
    run_id = resp.json()["id"]

    status_resp = await client.get(f"/api/v1/agents/{run_id}/status", headers=headers)
    assert status_resp.json()["final_response"]

    list_resp = await client.get("/api/v1/memory", headers=headers)
    assert list_resp.status_code == 200
    assert list_resp.json() == []


async def test_agent_calls_low_risk_tool_and_completes(client):
    registered = await register(client)
    headers = auth_headers(registered["access_token"])

    resp = await client.post(
        "/api/v1/agents/run", json={"goal": "please give me a usage summary"}, headers=headers
    )
    assert resp.status_code == 200
    run_id = resp.json()["id"]

    status_resp = await client.get(f"/api/v1/agents/{run_id}/status", headers=headers)
    body = status_resp.json()
    assert body["status"] == "completed"
    assert body["tool_call_count"] == 1

    steps = body["steps"]
    types = [s["type"] for s in steps]
    assert "tool_call" in types
    assert "observation" in types
    assert any(s["tool_name"] == "usage.get_summary" for s in steps if s["tool_name"])


async def test_agent_run_steps_are_returned_in_actual_order(client):
    """A tool_call and its observation share one loop iteration's step_number by design (see
    app/agents/runner.py), so ordering by step_number alone doesn't guarantee the tool_call comes
    back before the observation it produced — Postgres is free to return same-step_number rows in
    either order without a secondary sort key. Real bug, caught live via the CLI printing an
    observation before its own tool_call; confirmed by querying this exact endpoint directly
    against the real backend, not a client-side rendering bug. list_agent_steps
    (app/agents/service.py) now orders by (step_number, created_at) — this asserts the actual
    causal order (tool_call, then observation, then final_response), not just that both types are
    present somewhere in the list."""
    registered = await register(client)
    headers = auth_headers(registered["access_token"])

    resp = await client.post(
        "/api/v1/agents/run", json={"goal": "please give me a usage summary"}, headers=headers
    )
    run_id = resp.json()["id"]

    status_resp = await client.get(f"/api/v1/agents/{run_id}/status", headers=headers)
    types = [s["type"] for s in status_resp.json()["steps"]]
    assert types == ["tool_call", "observation", "final_response"]


async def test_agent_stops_when_tool_call_budget_exceeded(client, monkeypatch):
    monkeypatch.setattr(get_settings(), "agent_max_tool_calls", 0)
    registered = await register(client)
    headers = auth_headers(registered["access_token"])

    resp = await client.post(
        "/api/v1/agents/run", json={"goal": "please give me a usage summary"}, headers=headers
    )
    assert resp.status_code == 200
    run_id = resp.json()["id"]

    status_resp = await client.get(f"/api/v1/agents/{run_id}/status", headers=headers)
    body = status_resp.json()
    assert body["status"] == "stopped"
    assert "max_tool_calls" in body["error_message"]


async def test_agent_stops_when_step_budget_exceeded(client, monkeypatch):
    monkeypatch.setattr(get_settings(), "agent_max_steps", 1)
    registered = await register(client)
    headers = auth_headers(registered["access_token"])

    resp = await client.post(
        "/api/v1/agents/run", json={"goal": "please give me a usage summary"}, headers=headers
    )
    assert resp.status_code == 200
    run_id = resp.json()["id"]

    status_resp = await client.get(f"/api/v1/agents/{run_id}/status", headers=headers)
    body = status_resp.json()
    assert body["status"] == "stopped"
    assert "max_steps" in body["error_message"]


async def test_agent_run_request_can_tighten_the_step_budget(client):
    """PRD §34's `agent.max_iterations` (cli/src/projectConfig.ts) — a client can ask for a
    smaller budget than the deployment's own default."""
    registered = await register(client)
    headers = auth_headers(registered["access_token"])

    resp = await client.post(
        "/api/v1/agents/run",
        json={"goal": "please give me a usage summary", "max_steps": 2},
        headers=headers,
    )
    assert resp.status_code == 200
    run_id = resp.json()["id"]

    status_resp = await client.get(f"/api/v1/agents/{run_id}/status", headers=headers)
    body = status_resp.json()
    assert body["max_steps"] == 2
    # step 1: tool_call + observation (one loop iteration); step 2: final_response — the minimum
    # this goal needs, so a budget of exactly 2 still genuinely completes rather than being cut off
    # (test_agent_stops_when_step_budget_exceeded, above, covers the budget=1 "cut off" case).
    assert body["status"] == "completed"


async def test_agent_run_request_cannot_loosen_the_step_budget(client, monkeypatch):
    """A client-requested max_steps higher than the deployment's own ceiling must be clamped
    down, never honored — otherwise a project's own config file becomes a way to bypass the
    operator's configured resource limit."""
    monkeypatch.setattr(get_settings(), "agent_max_steps", 3)
    registered = await register(client)
    headers = auth_headers(registered["access_token"])

    resp = await client.post(
        "/api/v1/agents/run",
        json={"goal": "please give me a usage summary", "max_steps": 999},
        headers=headers,
    )
    assert resp.status_code == 200
    run_id = resp.json()["id"]

    status_resp = await client.get(f"/api/v1/agents/{run_id}/status", headers=headers)
    assert status_resp.json()["max_steps"] == 3


async def test_agent_stops_waiting_approval_for_critical_tool_and_does_not_execute_it(client):
    registered = await register(client)
    headers = auth_headers(registered["access_token"])

    files = {"file": ("notes.txt", b"content that an agent will try to delete", "text/plain")}
    upload = await client.post("/api/v1/documents", files=files, headers=headers)
    document_id = upload.json()["id"]

    resp = await client.post(
        "/api/v1/agents/run",
        json={"goal": f"please get rid of document {document_id}"},
        headers=headers,
    )
    assert resp.status_code == 200
    run_id = resp.json()["id"]

    status_resp = await client.get(f"/api/v1/agents/{run_id}/status", headers=headers)
    body = status_resp.json()
    assert body["status"] == "waiting_approval"
    assert body["pending_execution_id"]

    list_resp = await client.get("/api/v1/documents", headers=headers)
    assert len(list_resp.json()) == 1


async def test_approving_agents_pending_tool_actually_executes_it(client):
    registered = await register(client)
    headers = auth_headers(registered["access_token"])

    files = {"file": ("notes.txt", b"content the agent will delete after approval", "text/plain")}
    upload = await client.post("/api/v1/documents", files=files, headers=headers)
    document_id = upload.json()["id"]

    run_resp = await client.post(
        "/api/v1/agents/run",
        json={"goal": f"please get rid of document {document_id}"},
        headers=headers,
    )
    agent_run_id = run_resp.json()["id"]

    paused_status = await client.get(f"/api/v1/agents/{agent_run_id}/status", headers=headers)
    execution_id = paused_status.json()["pending_execution_id"]

    approve_resp = await client.post(
        f"/api/v1/tools/executions/{execution_id}/approve", headers=headers
    )
    assert approve_resp.status_code == 200
    assert approve_resp.json()["output"]["deleted"] is True

    list_resp = await client.get("/api/v1/documents", headers=headers)
    assert list_resp.json() == []

    # The run itself must reflect the approval, not stay frozen at "waiting_approval" forever —
    # real bug, caught live: the Agents page kept showing "Waiting on your approval" indefinitely
    # even after the tool had genuinely run, because nothing updated the AgentRun/AgentStep rows
    # once approval happened outside the run loop (a separate request, after the original
    # /agents/run request had already returned).
    #
    # Beyond that: the run must actually *continue* after approval, not just hand back that one
    # tool's result and stop — a real Permission Engine has to let the agent keep working once a
    # human clears a risky step. approve_execution (app/tools/service.py) schedules a background
    # resume (app/agents/router.py's run_agent_in_background(resume=True)) that the test client
    # runs to completion before this POST returns (same synchronous-background-task behavior the
    # other tests in this file already rely on) — MockProvider sees the tool result and, since it
    # doesn't match any tool name, returns a final answer, adding one more "final_response" step.
    status_resp = await client.get(f"/api/v1/agents/{agent_run_id}/status", headers=headers)
    status_body = status_resp.json()
    assert status_body["status"] == "completed"
    assert status_body["pending_execution_id"] is None
    observation_step, final_step = status_body["steps"][-2:]
    assert observation_step["type"] == "observation"
    assert observation_step["content"] == {"deleted": True, "document_id": document_id}
    assert final_step["type"] == "final_response"
    assert status_body["final_response"]


async def test_rejecting_agents_pending_tool_marks_the_run_stopped(client):
    registered = await register(client)
    headers = auth_headers(registered["access_token"])

    files = {"file": ("notes.txt", b"content that should survive rejection", "text/plain")}
    upload = await client.post("/api/v1/documents", files=files, headers=headers)
    document_id = upload.json()["id"]

    run_resp = await client.post(
        "/api/v1/agents/run",
        json={"goal": f"please get rid of document {document_id}"},
        headers=headers,
    )
    agent_run_id = run_resp.json()["id"]

    paused_status = await client.get(f"/api/v1/agents/{agent_run_id}/status", headers=headers)
    execution_id = paused_status.json()["pending_execution_id"]

    reject_resp = await client.post(
        f"/api/v1/tools/executions/{execution_id}/reject",
        json={"reason": "not yet"},
        headers=headers,
    )
    assert reject_resp.status_code == 200

    list_resp = await client.get("/api/v1/documents", headers=headers)
    assert len(list_resp.json()) == 1

    status_resp = await client.get(f"/api/v1/agents/{agent_run_id}/status", headers=headers)
    status_body = status_resp.json()
    assert status_body["status"] == "stopped"
    assert status_body["pending_execution_id"] is None
    last_step = status_body["steps"][-1]
    assert last_step["content"] == {"rejected": True, "reason": "not yet"}


async def test_agent_handles_a_failed_tool_call_without_crashing(client):
    registered = await register(client)
    headers = auth_headers(registered["access_token"])

    # "document" matches only document.delete's keyword (not "delete" — that word now also
    # matches code.delete_file/host.delete_file, and MockProvider picks whichever registered
    # tool it checks first alphabetically, so this goal deliberately avoids it), but there's no
    # UUID in the message, so MockProvider can't fill the required document_id — the tool call
    # should fail schema validation and the agent should record that as an observation, not
    # crash the request.
    resp = await client.post(
        "/api/v1/agents/run", json={"goal": "please get rid of the document"}, headers=headers
    )

    assert resp.status_code == 200
    status_resp = await client.get(f"/api/v1/agents/{resp.json()['id']}/status", headers=headers)
    steps = status_resp.json()["steps"]
    error_observations = [
        s
        for s in steps
        if s["type"] == "observation"
        and s["tool_name"] == "document.delete"
        and "error" in s["content"]
    ]
    assert len(error_observations) == 1


async def test_agent_runs_and_status_are_tenant_scoped(client):
    tenant_a = await register(client, tenant_name="Tenant A", email="a@agents.dev")
    tenant_b = await register(client, tenant_name="Tenant B", email="b@agents.dev")
    headers_a = auth_headers(tenant_a["access_token"])
    headers_b = auth_headers(tenant_b["access_token"])

    resp = await client.post("/api/v1/agents/run", json={"goal": "hello"}, headers=headers_a)
    agent_run_id = resp.json()["id"]

    list_b = await client.get("/api/v1/agents", headers=headers_b)
    assert list_b.json() == []

    status_b = await client.get(f"/api/v1/agents/{agent_run_id}/status", headers=headers_b)
    assert status_b.status_code == 404


async def test_agent_run_with_unknown_model_returns_400(client):
    registered = await register(client)
    headers = auth_headers(registered["access_token"])

    resp = await client.post(
        "/api/v1/agents/run",
        json={"goal": "hello", "model": "nonsense-model-id"},
        headers=headers,
    )
    assert resp.status_code == 400
    assert "nonsense-model-id" in resp.json()["detail"]


async def test_agent_run_with_auto_model_completes_normally(client):
    """"auto" (or omitting model entirely) means the provider's own default — same convention
    ChatRequest.model already uses — so this must still work exactly like the no-model case, not
    get rejected as an "unknown" id."""
    registered = await register(client)
    headers = auth_headers(registered["access_token"])

    resp = await client.post(
        "/api/v1/agents/run",
        json={"goal": "what's the weather like today?", "model": "auto"},
        headers=headers,
    )
    assert resp.status_code == 200
    status_resp = await client.get(f"/api/v1/agents/{resp.json()['id']}/status", headers=headers)
    assert status_resp.json()["status"] == "completed"


async def test_run_agent_honors_a_cancellation_set_before_it_starts(client, session_factory):
    """run_agent() re-checks status from the DB every iteration (see app/agents/runner.py) so a
    separate POST /agents/{id}/cancel request can stop a genuinely in-progress run. There's no
    reliable way to interleave a real HTTP cancel mid-loop against MockProvider in this offline
    suite — it resolves too fast for any timing-based race to be deterministic — so this proves
    the check itself works the way it's meant to: pre-cancelling before the loop's very first
    iteration, and confirming it stops there without calling the model or recording any step,
    rather than plowing through regardless."""
    registered = await register(client)
    tenant_ctx = TenantContext(
        tenant_id=uuid.UUID(registered["tenant"]["id"]),
        user_id=uuid.UUID(registered["user"]["id"]),
        role=registered["user"]["role"],
        permissions=["*"],
    )

    async with session_factory() as session:
        agent_run = await create_agent_run(session, tenant_ctx, "please give me a usage summary")
        agent_run.status = "cancelled"
        await session.commit()

        provider = ModelRouter().get_provider()
        await run_agent(session, tenant_ctx, provider, agent_run)

        assert agent_run.status == "cancelled"
        assert agent_run.step_count == 0
        assert agent_run.completed_at is not None


async def test_cancel_endpoint_does_not_override_an_already_finished_run(client):
    registered = await register(client)
    headers = auth_headers(registered["access_token"])

    run_resp = await client.post(
        "/api/v1/agents/run", json={"goal": "what's the weather like today?"}, headers=headers
    )
    run_id = run_resp.json()["id"]

    status_before = await client.get(f"/api/v1/agents/{run_id}/status", headers=headers)
    assert status_before.json()["status"] == "completed"

    cancel_resp = await client.post(f"/api/v1/agents/{run_id}/cancel", headers=headers)
    assert cancel_resp.status_code == 200
    assert cancel_resp.json()["status"] == "completed"


async def test_cancel_endpoint_is_tenant_scoped(client):
    tenant_a = await register(client, tenant_name="Tenant A", email="a@cancel.dev")
    tenant_b = await register(client, tenant_name="Tenant B", email="b@cancel.dev")
    headers_a = auth_headers(tenant_a["access_token"])
    headers_b = auth_headers(tenant_b["access_token"])

    run_resp = await client.post("/api/v1/agents/run", json={"goal": "hello"}, headers=headers_a)
    run_id = run_resp.json()["id"]

    cancel_resp = await client.post(f"/api/v1/agents/{run_id}/cancel", headers=headers_b)
    assert cancel_resp.status_code == 404
