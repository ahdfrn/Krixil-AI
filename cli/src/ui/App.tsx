import React, { useCallback, useRef, useState } from "react";
import { Box, Text, useApp, useInput } from "ink";
import TextInput from "ink-text-input";
import { ApiError, KrixilApi, type AgentRun, type ModelInfo } from "../api.js";
import { autoCheckpoint, diffStatSinceCheckpoint, findLastCheckpoint, resetToBeforeCheckpoint } from "../checkpoint.js";
import { buildGoal } from "../goal.js";
import { describeApprovalPrompt } from "../render.js";
import { Banner } from "./Banner.js";
import { Transcript } from "./Transcript.js";

interface PendingConfirm {
  title: string;
  detail: string;
  approveLabel: string;
  rejectLabel: string;
}

interface HistoryEntry {
  key: string;
  goal: string;
  run: AgentRun;
}

function sleep(ms: number): Promise<void> {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

export function App({
  api,
  hostRoot,
  initialDir,
  initialModel,
  maxSteps,
  projectName,
}: {
  api: KrixilApi;
  hostRoot: string;
  initialDir: string;
  // .kirxil.yml's model.default/agent.max_iterations/project.name (PRD §34, cli/src/
  // projectConfig.ts) — resolved once in index.ts before this renders, not re-read per goal.
  initialModel?: string;
  maxSteps?: number;
  projectName?: string;
}) {
  const { exit } = useApp();
  const [dir] = useState(initialDir);
  const [model, setModel] = useState(initialModel ?? "auto");
  const [input, setInput] = useState("");
  const [history, setHistory] = useState<HistoryEntry[]>([]);
  const [notice, setNotice] = useState<string | null>(null);
  const [activeRunId, setActiveRunId] = useState<string | null>(null);
  const [elapsed, setElapsed] = useState(0);
  const [pendingConfirm, setPendingConfirm] = useState<PendingConfirm | null>(null);
  const activeRunIdRef = useRef<string | null>(null);
  const confirmResolveRef = useRef<((approved: boolean) => void) | null>(null);

  useInput((char, key) => {
    if (confirmResolveRef.current) {
      const lower = char.toLowerCase();
      if (lower === "y") {
        confirmResolveRef.current(true);
        confirmResolveRef.current = null;
      } else if (lower === "n" || key.escape) {
        confirmResolveRef.current(false);
        confirmResolveRef.current = null;
      }
      return;
    }
    if (key.ctrl && char === "c") {
      if (activeRunIdRef.current) {
        void api.cancel(activeRunIdRef.current);
      } else {
        exit();
        process.exit(0);
      }
    }
  });

  // Blocks on a real keypress (y/n, handled in useInput above) instead of guessing — shared by
  // the tool-approval pause below and by `/undo`'s "are you sure" gate, since both are the same
  // shape (show what's about to happen, wait for a real answer, act on it).
  const waitForConfirm = useCallback((title: string, detail: string, approveLabel = "approve", rejectLabel = "reject") => {
    return new Promise<boolean>((resolve) => {
      confirmResolveRef.current = resolve;
      setPendingConfirm({ title, detail, approveLabel, rejectLabel });
    });
  }, []);

  const pollRun = useCallback(
    async (runId: string, entryKey: string) => {
      const start = Date.now();
      for (;;) {
        let run: AgentRun;
        try {
          run = await api.getStatus(runId);
        } catch (err) {
          setNotice(err instanceof ApiError ? `Lost track of that run: ${err.detail}` : "Lost track of that run.");
          break;
        }
        setHistory((prev) => prev.map((h) => (h.key === entryKey ? { ...h, run } : h)));
        setElapsed(Math.floor((Date.now() - start) / 1000));

        if (run.status === "waiting_approval" && run.pending_execution_id) {
          const executionId = run.pending_execution_id;
          try {
            const execution = await api.getExecution(executionId);
            const { title, detail } = describeApprovalPrompt(execution.tool_name, execution.risk_level, execution.input);
            const approved = await waitForConfirm(title, detail);
            setPendingConfirm(null);
            if (approved) await api.approveExecution(executionId);
            else await api.rejectExecution(executionId, "rejected in interactive mode");
          } catch (err) {
            setPendingConfirm(null);
            setNotice(err instanceof ApiError ? err.detail : "Couldn't handle the pending approval.");
            break;
          }
          continue;
        }

        if (run.status !== "running") break;
        await sleep(1000);
      }
      activeRunIdRef.current = null;
      setActiveRunId(null);
    },
    [api, waitForConfirm],
  );

  const runGoal = useCallback(
    async (instruction: string) => {
      setNotice(null);
      const goalText = buildGoal(instruction, dir);
      const checkpointHash = await autoCheckpoint(process.cwd(), instruction);
      if (checkpointHash) setNotice(`Checkpointed ${checkpointHash} — \`kirxil undo\` (from a shell) can revert to this.`);
      let started;
      try {
        started = await api.runAgent(goalText, model, maxSteps);
      } catch (err) {
        setNotice(err instanceof ApiError ? `Couldn't start that run: ${err.detail}` : "Couldn't start that run.");
        return;
      }
      const key = started.id;
      activeRunIdRef.current = started.id;
      setActiveRunId(started.id);
      setHistory((prev) => [...prev, { key, goal: instruction, run: { ...started, steps: [] } }]);
      void pollRun(started.id, key);
    },
    [api, dir, model, maxSteps, pollRun],
  );

  async function handleSubmit(value: string) {
    setInput("");
    const trimmed = value.trim();
    if (!trimmed) return;

    if (trimmed === "/exit" || trimmed === "/quit") {
      exit();
      process.exit(0);
    }
    if (trimmed === "/help") {
      setNotice(
        "/model [id] — list or switch models\n/cwd — show the current folder\n" +
          "/undo — revert to the last kirxil checkpoint (git reset --hard, asks first)\n/exit — quit",
      );
      return;
    }
    if (trimmed === "/cwd") {
      setNotice(`Working in ${dir} under ${hostRoot}.`);
      return;
    }
    if (trimmed === "/undo") {
      if (activeRunIdRef.current) {
        setNotice("A run is already in progress — wait for it to finish or Ctrl+C to stop it.");
        return;
      }
      const cwd = process.cwd();
      const checkpoint = await findLastCheckpoint(cwd);
      if (!checkpoint) {
        setNotice("No kirxil checkpoint found here.");
        return;
      }
      const stat = await diffStatSinceCheckpoint(cwd, checkpoint);
      if (!stat.trim()) {
        setNotice("Nothing has changed since the last checkpoint.");
        return;
      }
      const approved = await waitForConfirm("Undo to right before the last checkpoint?", stat.trim(), "undo", "keep");
      setPendingConfirm(null);
      if (!approved) {
        setNotice("Cancelled — nothing changed.");
        return;
      }
      const result = await resetToBeforeCheckpoint(cwd, checkpoint);
      setNotice(result.ok ? "Reverted." : result.reason);
      return;
    }
    if (trimmed === "/model" || trimmed.startsWith("/model ")) {
      const arg = trimmed.slice("/model".length).trim();
      if (arg) {
        setModel(arg);
        setNotice(`Switched to ${arg}.`);
        return;
      }
      let models: ModelInfo[];
      try {
        models = await api.listModels();
      } catch {
        setNotice("Couldn't load the model list.");
        return;
      }
      setNotice(models.map((m) => `${m.id === model ? "*" : " "} ${m.name} (${m.id}) — ${m.description}`).join("\n"));
      return;
    }

    if (activeRunIdRef.current) {
      setNotice("A run is already in progress — wait for it to finish or Ctrl+C to stop it.");
      return;
    }
    void runGoal(trimmed);
  }

  return (
    <Box flexDirection="column">
      <Banner dir={dir} hostRoot={hostRoot} model={model} projectName={projectName} />
      {history.map((h) => (
        <Box key={h.key} marginBottom={1}>
          <Transcript
            goal={h.goal}
            steps={h.run.steps}
            status={h.run.status}
            elapsedSeconds={h.run.id === activeRunId ? elapsed : 0}
          />
        </Box>
      ))}
      {notice && (
        <Box marginBottom={1}>
          <Text dimColor>{notice}</Text>
        </Box>
      )}
      {pendingConfirm ? (
        <Box flexDirection="column" borderStyle="round" borderColor="yellow" paddingX={1}>
          <Text bold color="yellow">
            ⏸ {pendingConfirm.title}
          </Text>
          <Text dimColor>{pendingConfirm.detail}</Text>
          <Text>
            Press <Text bold>y</Text> to {pendingConfirm.approveLabel}, <Text bold>n</Text> to {pendingConfirm.rejectLabel}.
          </Text>
        </Box>
      ) : (
        <Box>
          <Text color="cyan" bold>
            kirxil {">"}{" "}
          </Text>
          <TextInput value={input} onChange={setInput} onSubmit={(v) => void handleSubmit(v)} />
        </Box>
      )}
    </Box>
  );
}
