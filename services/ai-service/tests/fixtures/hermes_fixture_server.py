"""A real, minimal HTTP+SSE server implementing Hermes's own documented "Runs API" shape
(POST /v1/runs, GET /v1/runs/{id}, GET /v1/runs/{id}/events SSE, POST /v1/runs/{id}/approval,
POST /v1/runs/{id}/stop) — verified directly against gateway/platforms/api_server_runs.py in the
real NousResearch/hermes-agent repo, not guessed. Used only by test_hermes_client.py/
test_hermes_runtime.py, so app/agents/hermes_client.py's real HTTP+SSE code paths are exercised
against a real server, not a mocked httpx transport — same "real fixture, not a mocked SDK"
discipline this codebase already uses for MCP (tests/fixtures/mcp_test_server*.py).

The run's exact behavior is scripted by the test itself: `input` (the goal string sent to
POST /v1/runs) is expected to be a JSON object `{"script": [...], "final_output": "..."}` — each
script item is `{"type": "tool.started"|"tool.completed"|"approval.request", "fields": {...}}`,
played in order. An "approval.request" item pauses the run (status -> "waiting_for_approval") and
waits for a real POST .../approval before continuing; anything but choice="once" ends the run as
"cancelled" with no further events. A plain non-JSON `input` runs no tools and completes
immediately with `input` echoed back as the output.

Run directly: `python tests/fixtures/hermes_fixture_server.py <port>`
"""

import asyncio
import json
import sys
import time
import uuid

import uvicorn
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, StreamingResponse

app = FastAPI()
_runs: dict[str, dict] = {}


def _parse_script(raw_input: str) -> tuple[list[dict], str]:
    try:
        parsed = json.loads(raw_input)
    except json.JSONDecodeError:
        return [], raw_input
    if not isinstance(parsed, dict) or "script" not in parsed:
        return [], raw_input
    return parsed["script"], parsed.get("final_output", "done")


async def _drive_run(run_id: str, script: list[dict], final_output: str) -> None:
    run = _runs[run_id]
    queue: asyncio.Queue = run["queue"]
    for item in script:
        event = {
            "event": item["type"],
            "run_id": run_id,
            "timestamp": time.time(),
            **item.get("fields", {}),
        }
        if item["type"] == "approval.request":
            run["status"] = "waiting_for_approval"
            await queue.put(event)
            await run["approval_event"].wait()
            run["approval_event"].clear()
            if run["approval_choice"] != "once":
                run["status"] = "cancelled"
                run["output"] = None
                await queue.put(None)
                return
            run["status"] = "running"
        else:
            await queue.put(event)
    run["status"] = "completed"
    run["output"] = final_output
    await queue.put(None)


@app.post("/v1/runs")
async def create_run(request: Request) -> dict:
    body = await request.json()
    goal = body.get("input", "")
    run_id = f"run_{uuid.uuid4().hex[:12]}"
    script, final_output = _parse_script(goal)
    _runs[run_id] = {
        "status": "running",
        "output": None,
        "queue": asyncio.Queue(),
        "approval_event": asyncio.Event(),
        "approval_choice": None,
    }
    asyncio.create_task(_drive_run(run_id, script, final_output))
    return {"run_id": run_id, "status": "started"}


@app.get("/v1/runs/{run_id}")
async def get_run(run_id: str):
    run = _runs.get(run_id)
    if run is None:
        return JSONResponse({"error": f"Run not found: {run_id}"}, status_code=404)
    return {
        "object": "hermes.run",
        "run_id": run_id,
        "status": run["status"],
        "output": run["output"],
    }


@app.get("/v1/runs/{run_id}/events")
async def run_events(run_id: str):
    run = _runs.get(run_id)
    if run is None:
        return JSONResponse({"error": f"Run not found: {run_id}"}, status_code=404)

    async def _gen():
        while True:
            event = await run["queue"].get()
            if event is None:
                break
            yield f"data: {json.dumps(event)}\n\n"

    return StreamingResponse(_gen(), media_type="text/event-stream")


@app.post("/v1/runs/{run_id}/approval")
async def approval(run_id: str, request: Request) -> dict:
    body = await request.json()
    run = _runs.get(run_id)
    if run is None:
        return JSONResponse({"error": f"Run not found: {run_id}"}, status_code=404)
    run["approval_choice"] = body.get("choice")
    run["approval_event"].set()
    return {"status": "ok"}


@app.post("/v1/runs/{run_id}/stop")
async def stop(run_id: str) -> dict:
    run = _runs.get(run_id)
    if run is not None:
        run["status"] = "cancelled"
        await run["queue"].put(None)
    return {"status": "stopping"}


if __name__ == "__main__":
    uvicorn.run(app, host="127.0.0.1", port=int(sys.argv[1]), log_level="warning")
