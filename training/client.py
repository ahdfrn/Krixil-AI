"""Thin HTTP client for talking to the running Krixil api service. training/ deliberately has no
database driver or backend-framework dependency of its own — everything it needs (the training
dataset, readiness status, evaluation verdicts) comes over plain HTTP, reusing the api service's
existing auth and tenant-scoping rather than inventing a separate service-account system. See
docs/architecture/learning-and-memory.md Phase 3.
"""

import os

import httpx
from dotenv import load_dotenv

load_dotenv()

API_BASE_URL = os.environ.get("KRIXIL_API_BASE_URL", "http://localhost:8000/api/v1")
TENANT_SLUG = os.environ["KRIXIL_TENANT_SLUG"]
EMAIL = os.environ["KRIXIL_EMAIL"]
PASSWORD = os.environ["KRIXIL_PASSWORD"]
TOTP_CODE = os.environ.get("KRIXIL_TOTP_CODE")


class KrixilClient:
    def __init__(self) -> None:
        self._client = httpx.Client(base_url=API_BASE_URL, timeout=httpx.Timeout(120.0))
        self._token: str | None = None

    def _login(self) -> str:
        payload = {"tenant_slug": TENANT_SLUG, "email": EMAIL, "password": PASSWORD}
        if TOTP_CODE:
            payload["totp_code"] = TOTP_CODE
        response = self._client.post("/auth/login", json=payload)
        response.raise_for_status()
        return response.json()["access_token"]

    def _headers(self) -> dict:
        if self._token is None:
            self._token = self._login()
        return {"Authorization": f"Bearer {self._token}"}

    def get_dataset(self) -> list[dict]:
        response = self._client.get("/finetune/dataset", headers=self._headers())
        response.raise_for_status()
        return response.json()["rows"]

    def get_status(self) -> dict:
        response = self._client.get("/finetune/status", headers=self._headers())
        response.raise_for_status()
        return response.json()

    def start_self_initiated_run(self, example_count: int) -> str:
        response = self._client.post(
            "/finetune/runs/start",
            json={"example_count": example_count},
            headers=self._headers(),
        )
        response.raise_for_status()
        return response.json()["id"]

    def evaluate(self, model_tag: str) -> dict:
        response = self._client.post(
            "/finetune/evaluate", json={"model_tag": model_tag}, headers=self._headers()
        )
        response.raise_for_status()
        return response.json()

    def report(
        self,
        run_id: str,
        status: str,
        *,
        candidate_tag: str | None = None,
        promoted_tag: str | None = None,
        eval_pass_count: int | None = None,
        eval_fail_count: int | None = None,
        regression: bool | None = None,
        detail: str | None = None,
    ) -> None:
        response = self._client.post(
            "/finetune/report",
            json={
                "run_id": run_id,
                "status": status,
                "candidate_tag": candidate_tag,
                "promoted_tag": promoted_tag,
                "eval_pass_count": eval_pass_count,
                "eval_fail_count": eval_fail_count,
                "regression": regression,
                "detail": detail,
            },
            headers=self._headers(),
        )
        response.raise_for_status()
