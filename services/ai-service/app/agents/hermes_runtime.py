"""Translates Hermes's real HTTP+SSE Runs API (app/agents/hermes_client.py) into the exact same
real AgentStep/AgentRun/ToolExecution rows the native runner (app/agents/runner.py) produces, so
the CLI's Transcript.tsx and permission panel render a Hermes-originated run identically with zero
changes. Krixil's own Permission Engine stays the single source of truth for every tool approval —
never a second, parallel one — per the user's own explicit, confirmed requirement: a Hermes tool
call always becomes a real ToolExecution row, resolved through the exact same
approve/reject_execution endpoints a native HIGH-risk tool call already uses.
"""

import json
import uuid
from datetime import UTC, datetime

from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.hermes_client import (
    HermesClientError,
    get_hermes_run_status,
    resolve_hermes_approval,
    start_hermes_run,
    stop_hermes_run,
    stream_hermes_events,
)
from app.agents.runner import record_agent_step
from app.agents.service import get_agent_run_or_404
from app.core.audit import record_audit_log
from app.core.logging import get_logger
from app.db.session import AsyncSessionLocal
from app.models.tool_execution import ToolExecution
from app.tenancy.context import TenantContext
from app.tools.base import RiskLevel
from app.tools.risk_rules import find_block_reason

logger = get_logger(__name__)

_TERMINAL_STATUS_MAP = {"completed": "completed", "failed": "failed", "cancelled": "cancelled"}


def hermes_action_details(event: dict) -> dict:
    """Normalize supported argument envelopes without discarding conflicting fields."""
    details = {}
    for key in ("args", "arguments", "input"):
        value = event.get(key)
        if isinstance(value, str):
            try:
                value = json.loads(value)
            except ValueError:
                raise ValueError("unparseable tool arguments") from None
        if value is not None and not isinstance(value, dict):
            raise ValueError("tool arguments must be an object")
        if value:
            details[key] = value
    for key in ("command", "path", "directory", "scope"):
        if event.get(key):
            details[key] = event[key]
    return details


def _commands(value):
    if isinstance(value, dict):
        for key, child in value.items():
            if key == "command" and isinstance(child, str):
                yield child
            yield from _commands(child)
    elif isinstance(value, list):
        for child in value:
            yield from _commands(child)


def _has_action(value) -> bool:
    if isinstance(value, dict):
        return any(
            _has_action(child) for key, child in value.items() if key not in {"scope", "directory"}
        )
    if isinstance(value, list):
        return any(_has_action(child) for child in value)
    if isinstance(value, str):
        return bool(value.strip())
    return value is not None


def classify_hermes_approval(event: dict) -> tuple[RiskLevel | None, str]:
    """The confirmed 3-tier unmapped-tool policy. Returns (None, reason) for a request this
    codebase auto-denies without ever asking a human (an opaque request with no usable tool
    name, or a real match against Krixil's existing destructive-command patterns — the latter is
    a real BLOCK, same bar as host.run_command's own risk_classifier, never just "ask a human"),
    or (RiskLevel.HIGH, "") for every other real, inspectable request — always shown to a human,
    never auto-allowed, "Allow once" only (enforced in the CLI, see cli/src/ui/App.tsx)."""
    try:
        details = hermes_action_details(event)
    except ValueError as exc:
        return None, f"insufficient information to evaluate risk: {exc}"
    for command in _commands(details):
        block_reason = find_block_reason(command)
        if block_reason is not None:
            return None, f"blocked: {block_reason}"
    tool = event.get("tool") or event.get("name")
    if not isinstance(tool, str) or not tool.strip() or not _has_action(details):
        return None, "insufficient information to evaluate risk"
    if tool.strip().lower() in {"execute", "run_command", "terminal", "shell", "bash"} and not any(
        command.strip() for command in _commands(details)
    ):
        return None, "insufficient information to evaluate risk: missing command"
    return RiskLevel.HIGH, ""


async def _create_hermes_tool_execution(
    session: AsyncSession, tenant_ctx: TenantContext, event: dict
) -> ToolExecution:
    tool = event.get("tool") or event.get("name") or "unknown"
    execution = ToolExecution(
        tenant_id=tenant_ctx.tenant_id,
        requested_by=tenant_ctx.user_id,
        tool_name=f"hermes.{tool}",
        risk_level=RiskLevel.HIGH.value,
        input=event,
        status="pending_approval",
    )
    session.add(execution)
    await session.flush()
    await record_audit_log(
        session,
        tenant_id=tenant_ctx.tenant_id,
        user_id=tenant_ctx.user_id,
        action="tool.approval_requested",
        resource=execution.tool_name,
        metadata={"execution_id": str(execution.id), "risk_level": "high", "runtime": "hermes"},
    )
    logger.info(
        "hermes_tool_approval_requested",
        tenant_id=str(tenant_ctx.tenant_id),
        tool_name=execution.tool_name,
        execution_id=str(execution.id),
    )
    return execution


async def _mark_failed(tenant_ctx: TenantContext, agent_run_id: uuid.UUID, message: str) -> None:
    async with AsyncSessionLocal() as session:
        agent_run = await get_agent_run_or_404(session, tenant_ctx, agent_run_id)
        agent_run.status = "failed"
        agent_run.error_message = message
        agent_run.completed_at = datetime.now(UTC)
        await _finish_execution(session, tenant_ctx, agent_run, {"error": message})
        await session.commit()


async def _finish_execution(session, tenant_ctx, agent_run, output: dict) -> None:
    """Keep approval distinct from completion; only result events establish success."""
    if not agent_run.pending_execution_id:
        return
    execution = await session.get(ToolExecution, agent_run.pending_execution_id)
    if execution is None or execution.tenant_id != tenant_ctx.tenant_id:
        return
    if execution.status != "running":
        return
    execution.output = output
    execution.status = "failed" if output.get("error") else "completed"
    execution.error_message = str(output["error"]) if output.get("error") else None
    execution.completed_at = datetime.now(UTC)
    agent_run.pending_execution_id = None
    await record_audit_log(
        session,
        tenant_id=tenant_ctx.tenant_id,
        user_id=tenant_ctx.user_id,
        action=f"tool.{execution.status}",
        resource=execution.tool_name,
        metadata={"execution_id": str(execution.id), "runtime": "hermes"},
    )


async def _consume_hermes_events(
    tenant_ctx: TenantContext, agent_run_id: uuid.UUID, external_run_id: str, start_step: int
) -> None:
    """The real SSE-consumption loop, shared by a fresh run and a post-approval continuation
    (re-subscribing GET /v1/runs/{id}/events genuinely re-attaches to the same still-alive Hermes
    run_id — Hermes doesn't need to be told this is a "resume", only Krixil's own side does).
    A fresh AsyncSessionLocal() per event, same isolation reasoning as
    app/agents/swarm.py's _run_child_swarm_member — this loop can pause for many minutes waiting
    on a human approval, far longer than any single DB session should stay open."""
    step_number = start_step
    open_tool_step: int | None = None

    try:
        async for event in stream_hermes_events(external_run_id):
            async with AsyncSessionLocal() as session:
                agent_run = await get_agent_run_or_404(session, tenant_ctx, agent_run_id)
                await session.refresh(agent_run, attribute_names=["status"])
                if agent_run.status == "cancelled":
                    await _finish_execution(
                        session, tenant_ctx, agent_run, {"error": "Hermes run cancelled"}
                    )
                    try:
                        await stop_hermes_run(external_run_id)
                    except HermesClientError:
                        logger.warning("hermes_stop_on_cancel_failed", run_id=external_run_id)
                    agent_run.completed_at = datetime.now(UTC)
                    await session.commit()
                    return

                kind = event.get("event")
                if kind == "tool.started":
                    step_number += 1
                    open_tool_step = step_number
                    agent_run.tool_call_count += 1
                    agent_run.step_count = step_number
                    await record_agent_step(
                        session,
                        agent_run,
                        step_number,
                        "tool_call",
                        tool_name=event.get("tool"),
                        content={"preview": event.get("preview")},
                    )
                elif kind == "tool.completed":
                    output = {"duration": event.get("duration")}
                    for key in ("output", "stdout", "stderr", "exit_code", "timed_out"):
                        if key in event:
                            output[key] = event[key]
                    if event.get("error"):
                        output["error"] = event["error"]
                    elif event.get("timed_out") or event.get("exit_code", 0) != 0:
                        output["error"] = "Hermes tool failed or timed out"
                    if agent_run.pending_execution_id:
                        execution = await session.get(ToolExecution, agent_run.pending_execution_id)
                        if execution and execution.tool_name == f"hermes.{event.get('tool')}":
                            await _finish_execution(session, tenant_ctx, agent_run, output)
                    await record_agent_step(
                        session,
                        agent_run,
                        open_tool_step or step_number,
                        "observation",
                        tool_name=event.get("tool"),
                        content=output,
                    )
                elif kind == "approval.request":
                    step_number += 1
                    risk, reason = classify_hermes_approval(event)
                    if risk is None:
                        await record_agent_step(
                            session,
                            agent_run,
                            step_number,
                            "observation",
                            tool_name=event.get("tool") or event.get("name"),
                            content={"status": "denied", "reason": reason},
                        )
                        agent_run.step_count = step_number
                        await session.commit()
                        try:
                            await resolve_hermes_approval(
                                external_run_id, "deny", event.get("request_id")
                            )
                        except HermesClientError:
                            logger.warning(
                                "hermes_auto_deny_failed", run_id=external_run_id, reason=reason
                            )
                        continue
                    execution = await _create_hermes_tool_execution(session, tenant_ctx, event)
                    agent_run.status = "waiting_approval"
                    agent_run.pending_execution_id = execution.id
                    agent_run.step_count = step_number
                    await record_agent_step(
                        session,
                        agent_run,
                        step_number,
                        "observation",
                        tool_name=event.get("tool") or event.get("name"),
                        content={"status": "pending_approval", "execution_id": str(execution.id)},
                    )
                    await session.commit()
                    # Mirrors native's own "pause = stop this task" shape (runner.py's
                    # waiting_approval break) — a human action (app/tools/router.py's approve/
                    # reject branch for runtime="hermes") schedules the continuation.
                    return
                elif kind == "run.cancelled":
                    await _finish_execution(
                        session, tenant_ctx, agent_run, {"error": "Hermes run cancelled"}
                    )
                    agent_run.status = "cancelled"
                    agent_run.completed_at = datetime.now(UTC)
                    await session.commit()
                    return
                else:
                    # reasoning.available, subagent.start/complete, message.delta, etc. — read,
                    # not persisted this pass (see the plan's explicit "not this pass" list).
                    logger.debug("hermes_event_not_persisted", event_kind=kind)
                    continue
                await session.commit()
    except HermesClientError as exc:
        await _mark_failed(tenant_ctx, agent_run_id, f"Lost connection to Hermes: {exc}")
        return

    # Stream ended (Hermes closed the connection) — fetch the authoritative terminal status.
    try:
        final = await get_hermes_run_status(external_run_id)
    except HermesClientError as exc:
        await _mark_failed(tenant_ctx, agent_run_id, f"Couldn't fetch final Hermes status: {exc}")
        return

    async with AsyncSessionLocal() as session:
        agent_run = await get_agent_run_or_404(session, tenant_ctx, agent_run_id)
        final_output = final.get("output")
        status = _TERMINAL_STATUS_MAP.get(str(final.get("status")), "failed")
        agent_run.status = status
        agent_run.final_response = final_output if status == "completed" else None
        if status != "completed":
            hermes_status = final.get("status")
            agent_run.error_message = (
                final_output or f"Hermes run ended with status '{hermes_status}'."
            )
        agent_run.step_count = step_number + 1
        agent_run.completed_at = datetime.now(UTC)
        await _finish_execution(
            session,
            tenant_ctx,
            agent_run,
            {"error": "Hermes stream ended without a matching tool result"},
        )
        await record_agent_step(
            session,
            agent_run,
            step_number + 1,
            "final_response",
            content={"content": final_output},
        )


async def run_hermes_agent_in_background(
    tenant_id: uuid.UUID,
    user_id: uuid.UUID,
    role: str,
    permissions: list[str],
    agent_run_id: uuid.UUID,
    model_id: str | None,
) -> None:
    """Starts a brand-new Hermes run for agent_run_id's real goal, then consumes its real event
    stream. Same detached-TenantContext/own-AsyncSessionLocal shape as run_agent_in_background
    (app/agents/router.py) and _run_child_swarm_member (app/agents/swarm.py)."""
    tenant_ctx = TenantContext(
        tenant_id=tenant_id, user_id=user_id, role=role, permissions=permissions
    )
    async with AsyncSessionLocal() as session:
        agent_run = await get_agent_run_or_404(session, tenant_ctx, agent_run_id)
        try:
            external_run_id = await start_hermes_run(agent_run.goal)
        except HermesClientError as exc:
            agent_run.status = "failed"
            agent_run.error_message = f"Couldn't start Hermes run: {exc}"
            agent_run.completed_at = datetime.now(UTC)
            await session.commit()
            return
        agent_run.external_run_id = external_run_id
        agent_run.status = "running"
        await session.commit()

    await _consume_hermes_events(tenant_ctx, agent_run_id, external_run_id, start_step=0)


async def resume_hermes_agent_in_background(
    tenant_id: uuid.UUID,
    user_id: uuid.UUID,
    role: str,
    permissions: list[str],
    agent_run_id: uuid.UUID,
) -> None:
    """Re-subscribes to an already-running Hermes run's real event stream after a human resolved
    a pending approval (app/tools/router.py's approve/reject branch for runtime="hermes") — the
    real Hermes run never stopped server-side, only Krixil's own consumption of it paused."""
    tenant_ctx = TenantContext(
        tenant_id=tenant_id, user_id=user_id, role=role, permissions=permissions
    )
    async with AsyncSessionLocal() as session:
        agent_run = await get_agent_run_or_404(session, tenant_ctx, agent_run_id)
        external_run_id = agent_run.external_run_id
        start_step = agent_run.step_count
        agent_run.status = "running"
        await session.commit()

    if external_run_id is None:  # pragma: no cover - defensive, cannot happen via the real flow
        await _mark_failed(tenant_ctx, agent_run_id, "Missing Hermes external_run_id on resume.")
        return

    await _consume_hermes_events(tenant_ctx, agent_run_id, external_run_id, start_step=start_step)
