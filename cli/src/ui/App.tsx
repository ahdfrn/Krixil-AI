import React, { useCallback, useRef, useState } from "react";
import { Box, Text, useApp, useInput } from "ink";
import TextInput from "ink-text-input";
import { ApiError, KrixilApi, type AgentRun } from "../api.js";
import { autoCheckpoint, diffStatSinceCheckpoint, findLastCheckpoint, resetToBeforeCheckpoint } from "../checkpoint.js";
import { buildGoal } from "../goal.js";
import { loadProjectConfig } from "../projectConfig.js";
import { describeApprovalPrompt, testAttemptOutcomes } from "../render.js";
import { buildVerbInstruction } from "../verbs.js";
import { formatVerifyResultLines, runVerifyPipeline } from "../verify.js";
import { Banner } from "./Banner.js";
import { CommandPalette } from "./CommandPalette.js";
import { PlanPanel } from "./PlanPanel.js";
import { ModelPicker, type ModelChoice } from "./ModelPicker.js";
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
  initialRuntime,
  maxSteps,
  projectName,
}: {
  api: KrixilApi;
  hostRoot: string;
  initialDir: string;
  // .kirxil.yml's model.default/agent.max_iterations/agent.runtime/project.name (PRD §34,
  // cli/src/projectConfig.ts) — resolved once in index.ts before this renders, not re-read per
  // goal.
  initialModel?: string;
  initialRuntime?: "native" | "hermes";
  maxSteps?: number;
  projectName?: string;
}) {
  const { exit } = useApp();
  const [dir] = useState(initialDir);
  const [model, setModel] = useState(initialModel ?? "auto");
  const [mode, setMode] = useState<"chat" | "code">("chat");
  const [modelPickerOpen, setModelPickerOpen] = useState(false);
  const [runtime] = useState<"native" | "hermes">(initialRuntime ?? "native");
  const [input, setInput] = useState("");
  const [chats, setChats] = useState<{ question: string; answer: string }[]>([]);
  const conversationRef = useRef<string | undefined>(undefined);
  const chatAbortRef = useRef<AbortController | null>(null);
  const [paletteOpen, setPaletteOpen] = useState(false);
  const [activity, setActivity] = useState<string | null>(null);
  const busyRef = useRef(false);
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
    if (key.ctrl && char === "c") {
      if (modelPickerOpen) { setModelPickerOpen(false); return; }
      if (chatAbortRef.current) { chatAbortRef.current.abort(); return; }
      if (confirmResolveRef.current) resolveConfirm(false);
      if (activeRunIdRef.current) {
        void api.cancel(activeRunIdRef.current).catch(() => setNotice("Couldn't stop the run. Try again."));
      } else if (!busyRef.current) {
        exit();
      }
      return;
    }
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
    // Everything below only makes sense against the plain goal prompt, not while a typed-CONFIRM
    // dialog (its own separate typedConfirmValue state) is open — the branches above already
    // return for every other confirm shape, but a CRITICAL typed-confirm falls through here for
    // any key except Escape, so this needs its own explicit guard.
    if (pendingConfirm) return;
    if (modelPickerOpen) return;
    if (key.ctrl && char === "k") {
      setPaletteOpen((open) => !open);
      return;
    }
    if (paletteOpen) return;
    if (key.tab) {
      if (busyRef.current) { setNotice("Wait for the active task before switching mode."); return; }
      const nextMode = mode === "chat" ? "code" : "chat";
      setMode(nextMode);
      if (nextMode === "code" && model === "nvidia") {
        setModel("auto");
        setNotice("Code uses Auto. NVIDIA is limited to public chat without project access.");
      }
      return;
    }
    // Clears the visible run history the same way a real terminal's Ctrl+L/`clear` does — Ink
    // appends to normal scrollback rather than taking over an alt-screen, so this can't erase what
    // your terminal already printed, only what this app renders going forward.
    if (key.ctrl && char === "l") {
      setHistory((entries) => entries.filter((entry) => entry.run.id === activeRunIdRef.current));
      setNotice(null);
      if (!chatAbortRef.current) setChats([]);
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
      if (busyRef.current) return;
      busyRef.current = true;
      if (model === "nvidia") setModel("auto");
      setActivity("Starting run…");
      setElapsed(0);
      let buildNext = false;
      try {
        setNotice(null);
        const instruction = verb ? buildVerbInstruction(verb, rawGoal) : rawGoal;
        const goalText = buildGoal(instruction, dir);
        const checkpointHash = await autoCheckpoint(process.cwd(), rawGoal);
        if (checkpointHash) setNotice(`Checkpointed ${checkpointHash} — \`kirxil undo\` (from a shell) can revert to this.`);
        let started;
        try {
          started = await api.runAgent(goalText, model === "nvidia" ? "auto" : model, maxSteps, runtime);
        } catch (err) {
          setNotice(err instanceof ApiError ? `Couldn't start that run: ${err.detail}` : "Couldn't start that run.");
          return;
        }
        const key = started.id;
        activeRunIdRef.current = started.id;
        setActiveRunId(started.id);
        setActivity(verb === "plan" ? "Planning" : "Running");
        setHistory((prev) => [...prev, { key, goal: rawGoal, run: { ...started, steps: [] }, isPlan: verb === "plan" }]);
        const finalRun = await pollRun(started.id, key);
        if (verb === "plan" && finalRun?.status === "completed") {
          const approved = await waitForConfirm(
            "Run `kirxil build` with this goal now?",
            "The plan above is read-only — nothing has changed yet.",
            "build",
            "skip",
          );
          buildNext = approved;
        }
        // Real, deterministic check instead of trusting the model's own "Review" phase narration —
        // same .kirxil.yml `verify:` pipeline `kirxil build`/`kirxil verify` use (verify.ts).
        if (verb === "build" && finalRun?.status === "completed") {
          const verifySteps = loadProjectConfig()?.verify;
          if (verifySteps && verifySteps.length > 0) {
            setNotice("Running verification pipeline (.kirxil.yml's verify:)...");
            setActivity("Verifying");
            const verifyResult = await runVerifyPipeline(verifySteps, process.cwd());
            setNotice(formatVerifyResultLines(verifyResult).join("\n"));
          }
        }
      } catch (err) {
        setNotice(err instanceof Error ? err.message : "The task could not finish.");
      } finally {
        busyRef.current = false;
        setActivity(null);
      }
      if (buildNext) void runGoal(rawGoal, "build");
    },
    [api, dir, model, runtime, maxSteps, pollRun, waitForConfirm],
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
      if (busyRef.current) {
        setNotice("A task is still active. Stop it with Ctrl+C before exiting.");
        return;
      }
      exit();
      process.exit(0);
    }
    if (trimmed === "/help") {
      setNotice(
        "CHAT — conversation without tools; CODE — coding agent tasks\n/code <task> — run the coding agent\n/new — start a fresh chat\n" +
          "Tab — switch Chat / Code; / on an empty prompt — choose Auto / NVIDIA\n/model — open model menu\n/cwd — show the current folder\n" +
          "/plan <goal> — investigate and show a read-only plan, with a real handoff into `kirxil build`\n" +
          "/public <question> — Nemotron, non-sensitive question only (asks first)\n" +
          "/expand — toggle full tool output for the last run (long output is clipped by default)\n" +
          "/undo — revert to the last kirxil checkpoint (git reset --hard, asks first)\n/exit — quit\n" +
          "Ctrl+K — command palette · ↑/↓ — input history · Ctrl+L — clear finished runs",
      );
      return;
    }
    if (trimmed === "/public" || trimmed.startsWith("/public ") ||
        (!trimmed.startsWith("/") && mode === "chat" && model === "nvidia")) {
      const message = trimmed.startsWith("/public") ? trimmed.slice(7).trim() : trimmed;
      if (!message) { setNotice("Usage: /public <non-sensitive question> — Nemotron, one-shot, no tools."); return; }
      if (busyRef.current) { setNotice("Wait for the active task to finish first."); return; }
      if (message.length > 4000) { setNotice("Public questions are limited to 4000 characters."); return; }
      busyRef.current = true;
      try {
        const approved = await waitForConfirm(
          "Send this non-sensitive question to NVIDIA Nemotron via OpenRouter?",
          "NVIDIA logs usage for security and product improvement. Do NOT send secrets, private code, or personal data. " +
            "Only the question below is sent; no project context, chat history, memory, or tools. This cannot detect/redact secrets for you.\n\n" + message,
          "send once", "cancel",
        );
        if (!approved) { setNotice("Cancelled. Nothing sent to the public model."); return; }
        setActivity("Nemotron · public question only");
        const controller = new AbortController();
        chatAbortRef.current = controller;
        const response = await api.publicChat(message, controller.signal);
        setChats((previous) => [...previous, { question: `[PUBLIC · standalone] ${message}`, answer: response.content }]);
        setNotice(`Answered by ${response.provider} · ${response.model}. Not added to regular chat context.`);
      } catch (err) {
        setNotice(chatAbortRef.current?.signal.aborted ? "Stopped waiting; the public provider may still finish processing." :
          err instanceof Error ? err.message : "Public model request failed.");
      } finally {
        chatAbortRef.current = null;
        busyRef.current = false;
        setActivity(null);
      }
      return;
    }
    if (trimmed === "/new") {
      if (busyRef.current) { setNotice("Wait for the active task to finish first."); return; }
      conversationRef.current = undefined;
      setChats([]);
      setNotice("New chat started. Previous conversations remain stored on the server.");
      return;
    }
    if (trimmed === "/code" || trimmed.startsWith("/code ")) {
      const task = trimmed.slice(5).trim();
      if (!task) { setNotice("Usage: /code <task>. Plain text is chat without tools."); return; }
      if (busyRef.current) { setNotice("A task is already active."); return; }
      setMode("code");
      if (model === "nvidia") setModel("auto");
      void runGoal(task, "build");
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
      if (busyRef.current) {
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
      if (busyRef.current) {
        setNotice("A run is already in progress — wait for it to finish or Ctrl+C to stop it.");
        return;
      }
      void runGoal(goalArg, "plan");
      return;
    }
    if (trimmed === "/model" || trimmed.startsWith("/model ")) {
      if (busyRef.current) { setNotice("Wait for the active task before switching model."); return; }
      const arg = trimmed.slice("/model".length).trim().toLowerCase();
      if (!arg) setModelPickerOpen(true);
      else if (arg === "auto" || arg === "nvidia") selectModel(arg);
      else setNotice("Choose Auto or NVIDIA. Press / on an empty prompt to open the menu.");
      return;
    }

    if (trimmed.startsWith("/")) {
      setNotice(`Unknown command: ${trimmed.split(/\s/)[0]}. Use Ctrl+K or /help to see commands.`);
      return;
    }
    if (busyRef.current) {
      setNotice("A run is already in progress — wait for it to finish or Ctrl+C to stop it.");
      return;
    }
    if (mode === "code") {
      void runGoal(trimmed, "build");
      return;
    }
    busyRef.current = true;
    setActivity("Chatting · no tools");
    setNotice(null);
    const controller = new AbortController();
    chatAbortRef.current = controller;
    setChats((previous) => [...previous, { question: trimmed, answer: "Thinking…" }]);
    try {
      const response = await api.chat(trimmed, conversationRef.current, model, controller.signal);
      conversationRef.current = response.conversation_id;
      setNotice(`Answered by ${response.provider ?? "provider"} · ${response.model}`);
      setChats((previous) => previous.map((entry, index) => index === previous.length - 1
        ? { ...entry, answer: response.message.content } : entry));
    } catch (err) {
      const answer = controller.signal.aborted
        ? "Stopped waiting for the response. The server may still finish this message."
        : err instanceof Error ? `Chat failed: ${err.message}` : "Chat failed.";
      setChats((previous) => previous.map((entry, index) => index === previous.length - 1 ? { ...entry, answer } : entry));
    } finally {
      chatAbortRef.current = null;
      busyRef.current = false;
      setActivity(null);
    }
  }

  const lastRun = history.length > 0 ? history[history.length - 1]!.run : null;

  function selectModel(choice: ModelChoice) {
    setModel(choice);
    setModelPickerOpen(false);
    if (choice === "nvidia") {
      setMode("chat");
      setNotice("NVIDIA: public, standalone questions only. Each send requires confirmation; no project or chat history is shared.");
    }
  }

  return (
    <Box flexDirection="column">
      <Banner api={api} dir={dir} hostRoot={hostRoot} model={model} projectName={projectName} runtime={runtime} compact={history.length > 0 || chats.length > 0} />
      {chats.length > 0 && <Box flexDirection="column" marginBottom={1}>
        <Text dimColor>CONVERSATION · no tools</Text>
        {chats.map((chat, index) => <Box key={index} flexDirection="column" marginTop={1}>
          <Text bold>› {chat.question}</Text>
          <Text>{chat.answer}</Text>
        </Box>)}
      </Box>}
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
        <Box marginBottom={1} flexDirection="column" borderStyle="round" borderColor="gray" paddingX={1}>
          <Text bold>SESSION</Text>
          <Text>{notice}</Text>
        </Box>
      )}
      <Box paddingX={1} marginBottom={0} flexWrap="wrap" columnGap={1}>
        <Text bold={mode === "chat"} color={mode === "chat" ? "cyan" : "gray"}>{mode === "chat" ? "[CHAT]" : " CHAT "}</Text>
        <Text bold={mode === "code"} color={mode === "code" ? "yellow" : "gray"}>{mode === "code" ? "[CODE]" : " CODE "}</Text>
        <Text dimColor>·</Text>
        <Text color="#8b7bff">{model === "nvidia" ? "NVIDIA · public only" : model === "auto" ? "Auto" : model}</Text>
        <Text dimColor>· Tab mode · / model</Text>
      </Box>
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
      ) : modelPickerOpen ? (
        <ModelPicker current={model} onSelect={selectModel} onClose={() => setModelPickerOpen(false)} />
      ) : paletteOpen ? (
        <CommandPalette onClose={() => setPaletteOpen(false)} onSelect={(command) => {
          setInput(command);
          historyIndexRef.current = -1;
          setPaletteOpen(false);
        }} />
      ) : (
        <Box borderStyle="round" borderColor={mode === "code" ? "yellow" : "#8b7bff"} paddingX={1}>
          <Text color="#8b7bff" bold>
            {">"}{" "}
          </Text>
          <TextInput
            value={input}
            placeholder={activity ? "Task active…" : mode === "code" ? "Describe a coding task…" : model === "nvidia" ? "Ask a non-sensitive public question…" : "Type a message…"}
            onChange={(v) => {
              // A real edit while browsing history — not one of this component's own
              // programmatic setInput calls from the Up/Down handler above — snaps back to "not
              // browsing" so the next Up starts from the newest entry again, the current buffer
              // becoming the new draft.
              historyIndexRef.current = -1;
              if (v === "/" && input === "") {
                if (busyRef.current) setNotice("Wait for the active task before switching model.");
                else setModelPickerOpen(true);
                return;
              }
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
          activity={pendingConfirm ? "Awaiting approval" : activity ?? "Ready"}
          awaitingApproval={!!pendingConfirm}
        />
      </Box>
    </Box>
  );
}
