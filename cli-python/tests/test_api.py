import pytest

from krixil_cli.api import ApiError, KrixilApi

BASE_URL = "http://mock.krixil.test/api/v1"


@pytest.fixture
def api():
    client = KrixilApi(BASE_URL)
    yield client
    client.close()


def test_login_stores_token_and_returns_tenant_slug(api, httpx_mock):
    httpx_mock.add_response(
        url=f"{BASE_URL}/auth/login",
        json={
            "access_token": "tok-123",
            "token_type": "bearer",
            "expires_in": 3600,
            "user": {"id": "u1", "email": "a@b.dev"},
            "tenant": {"id": "t1", "name": "Acme", "slug": "acme-1"},
        },
    )
    result = api.login("acme-1", "a@b.dev", "correct-horse-battery")
    assert result.access_token == "tok-123"
    assert result.tenant_slug == "acme-1"


def test_login_failure_raises_api_error_with_detail(api, httpx_mock):
    httpx_mock.add_response(
        url=f"{BASE_URL}/auth/login", status_code=401, json={"detail": "Invalid credentials"}
    )
    with pytest.raises(ApiError, match="Invalid credentials"):
        api.login("acme-1", "a@b.dev", "wrong")


def test_run_agent_sends_goal_and_model(httpx_mock):
    api = KrixilApi(BASE_URL, access_token="tok-123")
    httpx_mock.add_response(
        url=f"{BASE_URL}/agents/run",
        json={
            "id": "run-1",
            "goal": "do the thing",
            "status": "running",
            "step_count": 0,
            "tool_call_count": 0,
            "max_steps": 8,
            "max_tool_calls": 5,
            "final_response": None,
            "error_message": None,
            "pending_execution_id": None,
            "created_at": "2026-09-01T00:00:00Z",
            "completed_at": None,
        },
    )
    run = api.run_agent("do the thing", "llama3.1:8b")
    assert run.id == "run-1"
    assert run.status == "running"
    request = httpx_mock.get_requests()[0]
    assert request.headers["authorization"] == "Bearer tok-123"
    api.close()


def test_get_status_returns_steps(httpx_mock):
    api = KrixilApi(BASE_URL, access_token="tok-123")
    httpx_mock.add_response(
        url=f"{BASE_URL}/agents/run-1/status",
        json={
            "id": "run-1",
            "goal": "do the thing",
            "status": "completed",
            "step_count": 1,
            "tool_call_count": 0,
            "max_steps": 8,
            "max_tool_calls": 5,
            "final_response": "Done.",
            "error_message": None,
            "pending_execution_id": None,
            "created_at": "2026-09-01T00:00:00Z",
            "completed_at": "2026-09-01T00:00:05Z",
            "steps": [
                {
                    "step_number": 1,
                    "type": "final_response",
                    "tool_name": None,
                    "content": {"content": "Done."},
                    "created_at": "2026-09-01T00:00:05Z",
                }
            ],
        },
    )
    run = api.get_status("run-1")
    assert run.status == "completed"
    assert len(run.steps) == 1
    api.close()


def test_calling_without_token_raises() -> None:
    api = KrixilApi(BASE_URL)
    with pytest.raises(RuntimeError, match="Not logged in"):
        api.list_models()
    api.close()
