"""Thin HTTP client for the Krixil api service's Agent endpoints — same shape as
apps/web/src/lib/api/agents.ts, just in Python. No SDK dependency, plain httpx, matching every
other native-Python piece of this project (training/client.py, app/ai/cloud_provider.py)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import httpx


class ApiError(Exception):
    def __init__(self, status_code: int, detail: str):
        super().__init__(detail)
        self.status_code = status_code
        self.detail = detail


@dataclass
class LoginResult:
    access_token: str
    tenant_slug: str


@dataclass
class AgentRun:
    id: str
    goal: str
    status: str
    step_count: int
    tool_call_count: int
    max_steps: int
    max_tool_calls: int
    final_response: str | None
    error_message: str | None
    pending_execution_id: str | None
    created_at: str
    completed_at: str | None
    steps: list[dict[str, Any]]


@dataclass
class ModelInfo:
    id: str
    name: str
    description: str


def _raise_for_error(response: httpx.Response) -> None:
    if response.status_code < 400:
        return
    try:
        detail = response.json().get("detail", response.text)
    except ValueError:
        detail = response.text
    if isinstance(detail, list):  # Pydantic validation errors come back as a list of objects.
        detail = "; ".join(str(d.get("msg", d)) for d in detail)
    raise ApiError(response.status_code, str(detail))


class KrixilApi:
    def __init__(self, base_url: str, access_token: str | None = None):
        self._client = httpx.Client(base_url=base_url, timeout=httpx.Timeout(60.0, connect=10.0))
        self._access_token = access_token

    def close(self) -> None:
        self._client.close()

    def _headers(self) -> dict[str, str]:
        if self._access_token is None:
            raise RuntimeError("Not logged in.")
        return {"Authorization": f"Bearer {self._access_token}"}

    def login(self, tenant_slug: str, email: str, password: str) -> LoginResult:
        response = self._client.post(
            "/auth/login",
            json={"tenant_slug": tenant_slug, "email": email, "password": password},
        )
        _raise_for_error(response)
        body = response.json()
        self._access_token = body["access_token"]
        return LoginResult(access_token=body["access_token"], tenant_slug=body["tenant"]["slug"])

    def list_models(self) -> list[ModelInfo]:
        response = self._client.get("/models", headers=self._headers())
        _raise_for_error(response)
        return [ModelInfo(**m) for m in response.json()]

    def run_agent(self, goal: str, model: str | None = None) -> AgentRun:
        response = self._client.post(
            "/agents/run", json={"goal": goal, "model": model}, headers=self._headers()
        )
        _raise_for_error(response)
        return AgentRun(**response.json(), steps=[])

    def get_status(self, run_id: str) -> AgentRun:
        response = self._client.get(f"/agents/{run_id}/status", headers=self._headers())
        _raise_for_error(response)
        return AgentRun(**response.json())

    def cancel(self, run_id: str) -> AgentRun:
        response = self._client.post(f"/agents/{run_id}/cancel", headers=self._headers())
        _raise_for_error(response)
        return AgentRun(**response.json(), steps=[])
