/**
 * A live orchestrator tree for `kirxil swarm` (PRD §27) — real per-child status, tool-call count,
 * and synthesis, polled from GET /agents/swarm/{id}/status (each child is a full, real AgentRun,
 * not a lightweight fabricated summary). Only used when stdout is a real TTY (index.ts checks
 * before rendering this); the existing plain console.log polling loop in index.ts's swarm action
 * stays the piped/scripted fallback, same reasoning as runOnce.ts vs ui/App.tsx for `kirxil run`.
 */
import React, { useEffect, useState } from "react";
import { Box, Text, useApp } from "ink";
import { ApiError, type KrixilApi, type SwarmRunDetail } from "../api.js";
import { swarmChildStatusIcon } from "../render.js";

const POLL_MS = 1000;

export function SwarmTree({ api, goal, swarmRunId }: { api: KrixilApi; goal: string; swarmRunId: string }) {
  const { exit } = useApp();
  const [swarm, setSwarm] = useState<SwarmRunDetail | null>(null);
  const [notice, setNotice] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    async function poll() {
      for (;;) {
        if (cancelled) return;
        let result: SwarmRunDetail;
        try {
          result = await api.getSwarmStatus(swarmRunId);
        } catch (err) {
          if (!cancelled) {
            setNotice(err instanceof ApiError ? `Lost track of that swarm: ${err.detail}` : "Lost track of that swarm.");
            exit();
          }
          return;
        }
        if (cancelled) return;
        setSwarm(result);
        if (result.status !== "running") {
          exit();
          return;
        }
        await new Promise((resolve) => setTimeout(resolve, POLL_MS));
      }
    }
    void poll();
    return () => {
      cancelled = true;
    };
  }, [api, swarmRunId, exit]);

  const children = swarm?.children ?? [];
  const goalById = new Map(children.map((c) => [c.id, c.original_goal ?? c.goal]));

  return (
    <Box flexDirection="column">
      <Text bold>› {goal}</Text>
      <Box height={1} />
      <Text color="cyan">
        ◉ ORCHESTRATOR{swarm ? ` — ${children.length} sub-task${children.length === 1 ? "" : "s"}` : " — decomposing…"}
      </Text>
      {children.map((child, i) => {
        const branch = i === children.length - 1 ? "└─" : "├─";
        const label = child.original_goal ?? child.goal;
        const waitingOn =
          child.status === "queued" && child.depends_on.length > 0
            ? ` — waiting on: ${child.depends_on.map((id) => goalById.get(id) ?? id).join(", ")}`
            : "";
        return (
          <Text key={child.id}>
            {"  "}
            {branch} {swarmChildStatusIcon(child.status)} {label}{" "}
            <Text dimColor>
              ({child.tool_call_count} tool call{child.tool_call_count === 1 ? "" : "s"} — {child.status}){waitingOn}
            </Text>
          </Text>
        );
      })}
      {notice && (
        <Box marginTop={1}>
          <Text color="red">{notice}</Text>
        </Box>
      )}
      {swarm?.status === "completed" && (
        <Box marginTop={1} flexDirection="column">
          <Text bold>SYNTHESIS</Text>
          <Text>{swarm.synthesis ?? ""}</Text>
        </Box>
      )}
      {swarm?.status === "failed" && (
        <Box marginTop={1}>
          <Text color="red">{swarm.error_message ?? "Swarm failed."}</Text>
        </Box>
      )}
    </Box>
  );
}
