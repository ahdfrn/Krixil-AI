from app.evaluation.base import EvalCase, EvalOutcome
from app.finetune.service import evaluate_candidate
from tests.fakes import FakeObjectStorage
from tests.helpers import auth_headers, register


async def _passing_case(session, tenant_ctx, provider, storage) -> EvalOutcome:
    return EvalOutcome(passed=True, details={})


_FAKE_CASES = [EvalCase(name="test.finetune_passes", category="test", run=_passing_case)]


async def test_dataset_returns_real_message_pairs(client):
    registered = await register(client)
    headers = auth_headers(registered["access_token"])

    await client.post(
        "/api/v1/chat",
        json={"message": "This is a long enough real question to pass the filter."},
        headers=headers,
    )

    resp = await client.get("/api/v1/finetune/dataset", headers=headers)
    assert resp.status_code == 200
    body = resp.json()
    assert body["example_count"] == 1
    assert body["rows"][0]["prompt"] == "This is a long enough real question to pass the filter."
    assert "Mock response to" in body["rows"][0]["completion"]


async def test_dataset_excludes_trivially_short_exchanges(client):
    registered = await register(client)
    headers = auth_headers(registered["access_token"])

    await client.post("/api/v1/chat", json={"message": "hi"}, headers=headers)

    resp = await client.get("/api/v1/finetune/dataset", headers=headers)
    assert resp.json()["example_count"] == 0


async def test_dataset_respects_memory_toggle(client):
    registered = await register(client)
    headers = auth_headers(registered["access_token"])

    await client.post(
        "/api/v1/chat", json={"message": "A real, long enough message to index."}, headers=headers
    )
    await client.patch("/api/v1/memory/settings", json={"enabled": False}, headers=headers)

    resp = await client.get("/api/v1/finetune/dataset", headers=headers)
    assert resp.json()["example_count"] == 0


async def test_status_reports_not_ready_below_threshold(client):
    registered = await register(client)
    headers = auth_headers(registered["access_token"])

    resp = await client.get("/api/v1/finetune/status", headers=headers)
    assert resp.status_code == 200
    body = resp.json()
    assert body["ready"] is False
    assert body["example_count"] == 0
    assert body["min_examples"] == 100


async def test_manual_run_creates_requested_row_visible_in_status(client):
    registered = await register(client)
    headers = auth_headers(registered["access_token"])

    trigger_resp = await client.post("/api/v1/finetune/run", headers=headers)
    assert trigger_resp.status_code == 200
    assert trigger_resp.json()["status"] == "requested"

    status_resp = await client.get("/api/v1/finetune/status", headers=headers)
    runs = status_resp.json()["runs"]
    assert len(runs) == 1
    assert runs[0]["status"] == "requested"


async def test_report_updates_run(client):
    registered = await register(client)
    headers = auth_headers(registered["access_token"])

    trigger_resp = await client.post("/api/v1/finetune/run", headers=headers)
    run_id = trigger_resp.json()["id"]

    report_resp = await client.post(
        "/api/v1/finetune/report",
        json={
            "run_id": run_id,
            "status": "promoted",
            "candidate_tag": "krixil-candidate-1",
            "promoted_tag": "krixil-personalized-2026-09-01",
            "eval_pass_count": 5,
            "eval_fail_count": 0,
            "regression": False,
        },
        headers=headers,
    )
    assert report_resp.status_code == 200
    body = report_resp.json()
    assert body["status"] == "promoted"
    assert body["promoted_tag"] == "krixil-personalized-2026-09-01"
    assert body["completed_at"] is not None


async def test_report_unknown_run_returns_404(client):
    registered = await register(client)
    headers = auth_headers(registered["access_token"])

    resp = await client.post(
        "/api/v1/finetune/report",
        json={"run_id": "00000000-0000-0000-0000-000000000000", "status": "failed"},
        headers=headers,
    )
    assert resp.status_code == 404


async def test_evaluate_candidate_reports_pass_fail_counts(client, session_factory):
    async with session_factory() as session:
        outcome = await evaluate_candidate(
            session, FakeObjectStorage(), "any-candidate-tag", cases=_FAKE_CASES
        )
        await session.commit()

    assert outcome.pass_count == 1
    assert outcome.fail_count == 0
