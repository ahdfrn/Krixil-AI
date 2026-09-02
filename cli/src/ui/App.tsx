import React, { useCallback, useRef, useState } from "react";
import { Box, Text, useApp, useInput } from "ink";
import TextInput from "ink-text-input";
import { ApiError, KrixilApi, type AgentRun, type ModelInfo } from "../api.js";
import { autoCheckpoint, diffStatSinceCheckpoint, findLastCheckpoint, resetToBeforeCheckpoint } from "../checkpoint.js";
import { buildGoal } from "../goal.js";
import { loadProjectConfig } from "../projectConfig.js";
import { describeApprovalPrompt, testAttemptOutcomes } from "../render.js";
import { buildVerbInstruction } from "../verbs.js";
import { formatVerifyResultLines, runVerifyPipeline } from "../verify.js";
import { Banner } from "./Banner.js";
import { PlanPanel } from "./PlanPanel.js";
import { StatusBar } from "./StatusBar.js";
import { RunSummary, Transcript } from "./Transcript.js";

interface PendingConfirm {
  title: string;
  detail: string;
  approveLabel: string;
  rejectLabel: string;
  riskLevel?: string;
  requireTypedConfirmation?: boolean;
}

interface HistoryEntry {
  key: string;
  goal: string;
  run: AgentRun;
  // Set for a run started via `/plan` — its final_response is a plan, shown in a bordered
  // PlanPanel instead of plain text, with a real "run kirxil build with this goal now?" handoff
  // once it completes (see runGoal's verb param below).
  isPlan?: boolean;
  // Toggled by `/expand` — content beyond MAX_OUTPUT_LINES was never printed at all, so this
  // reveals real content rather than un-clipping something already visible.
  expanded?: boolean;
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
  const [typedConfirmValue, setTypedConfirmValue] = useState("");
  const activeRunIdRef = useRef<string | null>(null);
  const confirmResolveRef = useRef<((approved: boolean) => void) | null>(null);
  // Real shell-style Up/Down history over what was actually submitted (goals and /commands
  // alike) — inputHistoryRef mirrors state in a ref too since useInput's callback closes over
  // stale state otherwise. historyIndexRef of -1 means "not browsing, showing the live draft";
  // draftRef holds what was being typed before the first Up so Down can restore it, the same way
  // a real shell does.
  const inputHistoryRef = useRef<string[]>([]);
  const historyIndexRef = useRef<number>(-1);
  const draftRef = useRef<string>("");

  const resolveConfirm = useCallback((approved: boolean) => {
    confirmResolveRef.current?.(approved);
    confirmResolveRef.current = null;
    setPendingConfirm(null);
    setTypedConfirmValue("");
  }, []);

  useInput((char, key) => {
    // A CRITICAL-risk pause takes real typed text ("CONFIRM") via the TextInput below instead of
    // a single y/n keypress — this handler must get out of its way rather than swallowing the
    // 'y'/'n'/'c'/etc. characters that are part of the word "CONFIRM" itself.
    if (confirmResolveRef.current && !pendingConfirm?.requireTypedConfirmation) {
      const lower = char.toLowerCase();
      if (lower === "y") {
        resolveConfirm(true);
      } else if (lower === "n" || key.escape) {
        resolveConfirm(false);
      }
      return;
    }
    if (confirmResolveRef.current && pendingConfirm?.requireTypedConfirmation && key.escape) {
      resolveConfirm(false);
      return;
    }
    if (key.ctrl && char === "c") {
      if (activeRunIdRef.current) {
        void api.cancel(activeRunIdRef.current);
      } else {
        exit();
        process.exit(0);
      }
      return;
    }
    // Everything below only makes sense against the plain goal prompt, not while a typed-CONFIRM
    // dialog (its own separate typedConfirmValue state) is open — the branches above already
    // return for every other confirm shape, but a CRITICAL typed-confirm falls through here for
    // any key except Escape, so this needs its own explicit guard.
    if (pendingConfirm) return;
    // Clears the visible run history the same way a real terminal's Ctrl+L/`clear` does — Ink
    // appends to normal scrollback rather than taking over an alt-screen, so this can't erase what
    // your terminal already printed, only what this app renders going forward.
    if (key.ctrl && char === "l") {
      setHistory([]);
      return;
    }
    if (key.upArrow) {
      const hist = inputHistoryRef.current;
      if (hist.length === 0) return;
      if (historyIndexRef.current === -1) {
        draftRef.current = input;
        historyIndexRef.current = hist.length - 1;
      } else if (historyIndexRef.current > 0) {
        historyIndexRef.current -= 1;
      }
      setInput(hist[historyIndexRef.current]!);
      return;
    }
    if (key.downArrow) {
      const hist = inputHistoryRef.current;
      if (historyIndexRef.current === -1) return;
      if (historyIndexRef.current < hist.length - 1) {
        historyIndexRef.current += 1;
        setInput(hist[historyIndexRef.current]!);
      } else {
        historyIndexRef.current = -1;
        setInput(draftRef.current);
      }
    }
  });

  // Blocks on a real answer (a y/n keypress, or typed "CONFIRM" for CRITICAL risk — both handled
  // in useInput above / the TextInput below) instead of guessing — shared by the tool-approval
  // pause below and by `/undo`'s "are you sure" gate, since both are the same shape (show what's
  // about to happen, wait for a real answer, act on it).
  const waitForConfirm = useCallback(
    (
      title: string,
      detail: string,
      approveLabel = "approve",
      rejectLabel = "reject",
      riskLevel?: string,
      requireTypedConfirmation = false,
    ) => {
      return new Promise<boolean>((resolve) => {
        confirmResolveRef.current = resolve;
        setPendingConfirm({ title, detail, approveLabel, rejectLabel, riskLevel, requireTypedConfirmation });
      });
    },
    [],
  );

  const pollRun = useCallback(
    async (runId: string, entryKey: string): Promise<AgentRun | undefined> => {
      const start = Date.now();
      let run: AgentRun | undefined;
      for (;;) {
        try {
          run = await api.getStatus(runId);
        } catch (err) {
          setNotice(err instanceof ApiError ? `Lost track of that run: ${err.detail}` : "Lost track of that run.");
          break;
        }
        setHistory((prev) => prev.map((h) => (h.key === entryKey ? { ...h, run: run! } : h)));
        setElapsed(Math.floor((Date.now() - start) / 1000));

        if (run.status === "waiting_approval" && run.pending_execution_id) {
          const executionId = run.pending_execution_id;
          try {
            const execution = await api.getExecution(executionId);
            const { title, detail, riskLevel, requireTypedConfirmation } = describeApprovalPrompt(
              execution.tool_name,
              execution.risk_level,
              execution.input,
            );
            const approved = await waitForConfirm(title, detail, "approve", "reject", riskLevel, requireTypedConfirmation);
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
      return run;
    },
    [api, waitForConfirm],
  );

  // verb undefined = the plain-typed-goal path (unchanged); "plan"/"build" wrap the raw goal via
  // verbs.ts's real instruction templates. A completed plan offers a real, awaited follow-up into
  // `kirxil build` with the exact same rawGoal — genuine chaining of two already-real commands,
  // not a new planning engine.
  const runGoal = useCallback(
    async (rawGoal: string, verb?: "plan" | "build") => {
      setNotice(null);
      const instruction = verb ? buildVerbInstruction(verb, rawGoal) : rawGoal;
      const goalText = buildGoal(instruction, dir);
      const checkpointHash = await autoCheckpoint(process.cwd(), rawGoal);
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
      setHistory((prev) => [...prev, { key, goal: rawGoal, run: { ...started, steps: [] }, isPlan: verb === "plan" }]);
      const finalRun = await pollRun(started.id, key);
      if (verb === "plan" && finalRun?.status === "completed") {
        const approved = await waitForConfirm(
          "Run `kirxil build` with this goal now?",
          "The plan above is read-only — nothing has changed yet.",
          "build",
          "skip",
        );
        if (approved) void runGoal(rawGoal, "build");
      }
      // Real, deterministic check instead of trusting the model's own "Review" phase narration —
      // same .kirxil.yml `verify:` pipeline `kirxil build`/`kirxil verify` use (verify.ts).
      if (verb === "build" && finalRun?.status === "completed") {
        const verifySteps = loadProjectConfig()?.verify;
        if (verifySteps && verifySteps.length > 0) {
          setNotice("Running verification pipeline (.kirxil.yml's verify:)...");
          const verifyResult = await runVerifyPipeline(verifySteps, process.cwd());
          setNotice(formatVerifyResultLines(verifyResult).join("\n"));
        }
      }
    },
    [api, dir, model, maxSteps, pollRun, waitForConfirm],
  );

  async function handleSubmit(value: string) {
    setInput("");
    const trimmed = value.trim();
    if (!trimmed) return;

    historyIndexRef.current = -1;
    draftRef.current = "";
    const hist = inputHistoryRef.current;
    if (hist[hist.length - 1] !== trimmed) inputHistoryRef.current = [...hist, trimmed];

    if (trimmed === "/exit" || trimmed === "/quit") {
      exit();
      process.exit(0);
    }
    if (trimmed === "/help") {
      setNotice(
        "/model [id] — list or switch models\n/cwd — show the current folder\n" +
          "/plan <goal> — investigate and show a read-only plan, with a real handoff into `kirxil build`\n" +
          "/expand — toggle full tool output for the last run (long output is clipped by default)\n" +
          "/undo — revert to the last kirxil checkpoint (git reset --hard, asks first)\n/exit — quit\n" +
          "↑/↓ — recall previously submitted goals/commands · Ctrl+L — clear this screen's history",
      );
      return;
    }
    if (trimmed === "/cwd") {
      setNotice(`Working in ${dir} under ${hostRoot}.`);
      return;
    }
    if (trimmed === "/expand") {
      if (history.length === 0) {
        setNotice("Nothing to expand yet.");
        return;
      }
      const lastKey = history[history.length - 1]!.key;
      let nowExpanded = false;
      setHistory((prev) =>
        prev.map((h) => {
          if (h.key !== lastKey) return h;
          nowExpanded = !h.expanded;
          return { ...h, expanded: nowExpanded };
        }),
      );
      setNotice(nowExpanded ? "Showing full tool output for the last run." : "Back to clipped tool output.");
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
    if (trimmed === "/plan" || trimmed.startsWith("/plan ")) {
      const goalArg = trimmed.slice("/plan".length).trim();
      if (!goalArg) {
        setNotice("Usage: /plan <goal>");
        return;
      }
      if (activeRunIdRef.current) {
        setNotice("A run is already in progress — wait for it to finish or Ctrl+C to stop it.");
        return;
      }
      void runGoal(goalArg, "plan");
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

  const lastRun = history.length > 0 ? history[history.length - 1]!.run : null;

  return (
    <Box flexDirection="column">
      <Banner api={api} dir={dir} hostRoot={hostRoot} model={model} projectName={projectName} />
      {history.map((h) => (
        <Box key={h.key} flexDirection="column" marginBottom={1}>
          <Transcript
            goal={h.goal}
            steps={h.isPlan ? h.run.steps.filter((s) => s.type !== "final_response") : h.run.steps}
            status={h.run.status}
            elapsedSeconds={h.run.id === activeRunId ? elapsed : 0}
            expanded={h.expanded ?? false}
          />
          {h.isPlan && h.run.status === "completed" && h.run.final_response && (
            <Box marginTop={1}>
              <PlanPanel planText={h.run.final_response} />
            </Box>
          )}
          {!h.isPlan && <RunSummary steps={h.run.steps} status={h.run.status} />}
        </Box>
      ))}
      {notice && (
        <Box marginBottom={1}>
          <Text dimColor>{notice}</Text>
        </Box>
      )}
      {pendingConfirm ? (
        <Box
          flexDirection="column"
          borderStyle="round"
          borderColor={pendingConfirm.riskLevel === "critical" ? "red" : "yellow"}
          paddingX={1}
        >
          <Text bold color={pendingConfirm.riskLevel === "critical" ? "red" : "yellow"}>
            ⏸ {pendingConfirm.title}
          </Text>
          {pendingConfirm.riskLevel && (
            <Text dimColor>
              Risk: <Text bold={pendingConfirm.riskLevel === "critical"}>{pendingConfirm.riskLevel.toUpperCase()}</Text>
            </Text>
          )}
          <Text dimColor>{pendingConfirm.detail}</Text>
          {pendingConfirm.requireTypedConfirmation ? (
            <Box marginTop={1}>
              <Text>
                Type <Text bold color="red">CONFIRM</Text> to proceed, or Esc to cancel:{" "}
              </Text>
              <TextInput
                value={typedConfirmValue}
                onChange={setTypedConfirmValue}
                onSubmit={(v) => resolveConfirm(v.trim().toUpperCase() === "CONFIRM")}
              />
            </Box>
          ) : (
            <Text>
              Press <Text bold>y</Text> to {pendingConfirm.approveLabel}, <Text bold>n</Text> to {pendingConfirm.rejectLabel}.
            </Text>
          )}
        </Box>
      ) : (
        <Box borderStyle="round" borderColor="#8b7bff" paddingX={1}>
          <Text color="#8b7bff" bold>
            {">"}{" "}
          </Text>
          <TextInput
            value={input}
            onChange={(v) => {
              // A real edit while browsing history — not one of this component's own
              // programmatic setInput calls from the Up/Down handler above — snaps back to "not
              // browsing" so the next Up starts from the newest entry again, the current buffer
              // becoming the new draft.
              historyIndexRef.current = -1;
              setInput(v);
            }}
            onSubmit={(v) => void handleSubmit(v)}
          />
        </Box>
      )}
      <Box marginTop={1}>
        <StatusBar
          toolCalls={lastRun ? lastRun.steps.filter((s) => s.type === "tool_call").length : 0}
          testOutcomes={lastRun ? testAttemptOutcomes(lastRun.steps) : []}
        />
      </Box>
    </Box>
  );
}
