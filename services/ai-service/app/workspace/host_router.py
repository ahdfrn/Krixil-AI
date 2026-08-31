"""Human-driven browsing of a real folder on this machine, via host-runner — same shape as
app/workspace/router.py's tenant-isolated equivalent, but proxied over HTTP since host-runner is
a separate native-Windows process, not something this container can touch directly. Bypasses the
Tool System entirely, same as /workspace/files already does for a human using the Code page
directly (as opposed to an Agent's tool call)."""

from collections.abc import Awaitable, Callable

import httpx
from fastapi import APIRouter, File, HTTPException, UploadFile, status
from pydantic import BaseModel

from app.core.config import get_settings

router = APIRouter(prefix="/host", tags=["workspace"])

_UNREACHABLE_DETAIL = (
    "host-runner isn't reachable — is it running? See services/host-runner/README.md."
)


class HostEntryOut(BaseModel):
    name: str
    path: str
    is_dir: bool
    size_bytes: int | None


class HostFileOut(BaseModel):
    path: str
    content: str


async def _proxy(call: Callable[[httpx.AsyncClient], Awaitable[httpx.Response]]) -> httpx.Response:
    """Runs one request against host-runner, translating its failure modes into the same
    HTTPException shapes every other router in this app already raises — the client-side code
    only ever needs to handle ApiError, not know host-runner is a separate process."""
    settings = get_settings()
    async with httpx.AsyncClient(
        base_url=settings.host_runner_url, timeout=settings.host_runner_timeout_seconds
    ) as client:
        try:
            response = await call(client)
            response.raise_for_status()
            return response
        except httpx.HTTPStatusError as exc:
            detail = exc.response.text
            try:
                detail = exc.response.json().get("detail", detail)
            except ValueError:
                pass
            raise HTTPException(status_code=exc.response.status_code, detail=detail) from exc
        except httpx.ConnectError as exc:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=_UNREACHABLE_DETAIL
            ) from exc


@router.get("/files", response_model=list[HostEntryOut])
async def get_files(path: str = ".") -> list[HostEntryOut]:
    response = await _proxy(lambda client: client.get("/files", params={"path": path}))
    return [HostEntryOut(**e) for e in response.json()]


@router.get("/files/content", response_model=HostFileOut)
async def get_file_content(path: str) -> HostFileOut:
    response = await _proxy(lambda client: client.get("/files/content", params={"path": path}))
    return HostFileOut(**response.json())


@router.post("/files", response_model=HostFileOut, status_code=status.HTTP_201_CREATED)
async def write_file(path: str, file: UploadFile = File(...)) -> HostFileOut:
    content = (await file.read()).decode("utf-8", errors="replace")
    response = await _proxy(
        lambda client: client.post("/files", json={"path": path, "content": content})
    )
    return HostFileOut(**response.json())


@router.delete("/files", status_code=status.HTTP_204_NO_CONTENT)
async def remove_file(path: str) -> None:
    await _proxy(lambda client: client.delete("/files", params={"path": path}))
