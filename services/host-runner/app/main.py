"""Runs natively on Windows, not in Docker — see docs/architecture/coding-agent.md ("Real
host-folder access") for why. Binds to 127.0.0.1 only (see run.py / README); this service has no
auth of its own, so it must never be reachable from outside this machine. Everything under
HOST_ROOT is fully readable/writable/executable, with no approval step and no sandbox — the one
remaining guardrail is path confinement to HOST_ROOT itself (app/fs.py)."""

import subprocess

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, status
from pydantic import BaseModel, Field

load_dotenv()

from app.fs import (  # noqa: E402  (must follow load_dotenv() — fs.py reads os.environ at call time)
    HostPathError,
    delete_file,
    host_root,
    list_files,
    read_file,
    resolve_host_path,
    search_files,
    write_file,
)

app = FastAPI(title="krixil-host-runner")


class FileEntryOut(BaseModel):
    name: str
    path: str
    is_dir: bool
    size_bytes: int | None


class FileContentOut(BaseModel):
    path: str
    content: str


class WriteFileRequest(BaseModel):
    path: str = Field(min_length=1, max_length=1000)
    content: str = Field(max_length=1_000_000)


class RunRequest(BaseModel):
    directory: str = Field(default=".", max_length=1000)
    command: str = Field(min_length=1, max_length=4000)
    timeout_seconds: int = Field(default=60, ge=1, le=600)


class RunResult(BaseModel):
    stdout: str
    stderr: str
    exit_code: int
    timed_out: bool


class SearchResultOut(BaseModel):
    path: str
    line_number: int
    line: str


@app.get("/health")
async def health() -> dict:
    return {"status": "ok", "host_root": str(host_root())}


@app.get("/files", response_model=list[FileEntryOut])
async def get_files(path: str = ".") -> list[FileEntryOut]:
    try:
        return [FileEntryOut(**e) for e in list_files(path)]
    except HostPathError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc


@app.get("/files/content", response_model=FileContentOut)
async def get_file_content(path: str) -> FileContentOut:
    try:
        return FileContentOut(path=path, content=read_file(path))
    except HostPathError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    except FileNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=f"'{path}' does not exist"
        ) from exc


@app.post("/files", response_model=FileContentOut, status_code=status.HTTP_201_CREATED)
async def post_file(payload: WriteFileRequest) -> FileContentOut:
    try:
        write_file(payload.path, payload.content)
    except HostPathError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    return FileContentOut(path=payload.path, content=payload.content)


@app.delete("/files", status_code=status.HTTP_204_NO_CONTENT)
async def remove_file(path: str) -> None:
    try:
        delete_file(path)
    except HostPathError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    except IsADirectoryError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail=f"'{path}' is a directory"
        ) from exc


@app.get("/search", response_model=list[SearchResultOut])
async def get_search(pattern: str, path: str = ".") -> list[SearchResultOut]:
    try:
        return [SearchResultOut(**r) for r in search_files(pattern, path)]
    except HostPathError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc


@app.post("/run", response_model=RunResult)
async def run_command(payload: RunRequest) -> RunResult:
    try:
        cwd = resolve_host_path(payload.directory)
    except HostPathError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    cwd.mkdir(parents=True, exist_ok=True)

    timed_out = False
    try:
        result = subprocess.run(
            payload.command,
            shell=True,
            cwd=str(cwd),
            capture_output=True,
            text=True,
            timeout=payload.timeout_seconds,
        )
        stdout, stderr, exit_code = result.stdout, result.stderr, result.returncode
    except subprocess.TimeoutExpired as exc:
        timed_out = True
        stdout = exc.stdout or ""
        stderr = exc.stderr or ""
        exit_code = -1

    return RunResult(stdout=stdout, stderr=stderr, exit_code=exit_code, timed_out=timed_out)
