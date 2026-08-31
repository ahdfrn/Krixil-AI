"use client";

import {
  Bot,
  Code2,
  File as FileIcon,
  Folder,
  Loader2,
  Save,
  TriangleAlert,
  Trash2,
  Upload,
  X,
} from "lucide-react";
import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { useEffect, useRef, useState } from "react";
import { toast } from "sonner";

import { StepView } from "@/components/agent-run/step-view";
import { formatBytes } from "@/components/chat/file-attachment-chip";
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from "@/components/ui/alert-dialog";
import { Button } from "@/components/ui/button";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Skeleton } from "@/components/ui/skeleton";
import { Textarea } from "@/components/ui/textarea";
import {
  getAgentRunStatus,
  listAgentRuns,
  runAgent,
  type AgentRunDetailOut,
} from "@/lib/api/agents";
import { ApiError } from "@/lib/api/client";
import {
  deleteHostFile,
  getHostFileContent,
  listHostFiles,
  uploadHostFile,
} from "@/lib/api/host";
import {
  deleteWorkspaceFile,
  getWorkspaceFileContent,
  listWorkspaceFiles,
  uploadWorkspaceFile,
} from "@/lib/api/workspace";
import { cn } from "@/lib/utils";
import { parseCodeGoal, type CodeRoot as Root } from "@/lib/utils/code-sessions";
import { useCodeSessionsStore } from "@/stores/code-sessions-store";

interface Entry {
  name: string;
  path: string;
  is_dir: boolean;
  size_bytes: number | null;
}

function listFiles(root: Root, dir: string): Promise<Entry[]> {
  return root === "workspace" ? listWorkspaceFiles(dir) : listHostFiles(dir);
}

function getFileContent(root: Root, path: string): Promise<{ content: string }> {
  return root === "workspace" ? getWorkspaceFileContent(path) : getHostFileContent(path);
}

function uploadFile(root: Root, path: string, file: File) {
  return root === "workspace" ? uploadWorkspaceFile(path, file) : uploadHostFile(path, file);
}

function deleteFile(root: Root, path: string): Promise<void> {
  return root === "workspace" ? deleteWorkspaceFile(path) : deleteHostFile(path);
}

// Scopes a plain instruction to whatever folder is currently open and tells the model which tool
// family to use — needed now that both code.* (isolated) and host.* (real, unsandboxed) tools are
// registered at once, so the model has to be told which one this goal means. Same "frame the same
// underlying goal" approach agents/page.tsx's buildResearchGoal already uses for Deep Research —
// no backend change, this is advisory framing; the real enforced boundary is path confinement
// (app/workspace/fs.py for the workspace, services/host-runner/app/fs.py for the host). The exact
// shape here ("Using your ... tools, work in/within ...") is what lib/utils/code-sessions.ts's
// parseCodeGoal() parses back out — keep them in sync if this changes.
function buildCodeGoal(instruction: string, dir: string, root: Root): string {
  const tools =
    root === "workspace"
      ? "code.list_files, code.read_file, code.write_file, code.run_command"
      : "host.list_files, host.read_file, host.write_file, host.run_command";
  const place = root === "workspace" ? "your coding workspace" : "the real folder on this machine";

  if (dir === ".") {
    return `Using your ${tools} tools, work in ${place}. Task: ${instruction}`;
  }
  return (
    `Using your ${tools} tools, work within the "${dir}" folder of ${place}. File paths ` +
    `are relative to the root, so prefix paths with "${dir}/" (e.g. "${dir}/main.py"). For shell ` +
    `commands that need to run inside that folder, start with \`cd ${dir} &&\`. ` +
    `Task: ${instruction}`
  );
}

export default function CodePage() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const loadCodeSessions = useCodeSessionsStore((s) => s.loadSessions);

  // Derived straight from the URL on every render — no separate useState to go stale. Clicking a
  // different session link only changes the query string on the *same* /code route (Next.js
  // doesn't remount the page for that), so anything stored as independent local state here would
  // keep showing the previous session's folder/history until a full reload (real bug, caught
  // live). useSearchParams() is itself reactive — a URL change re-renders this component with a
  // fresh value, so root/dir just naturally follow along.
  const root: Root = searchParams.get("root") === "host" ? "host" : "workspace";
  const dir = searchParams.get("dir") ?? ".";

  const [entries, setEntries] = useState<Entry[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [isUploading, setIsUploading] = useState(false);
  const fileInputRef = useRef<HTMLInputElement>(null);
  const [deleteTarget, setDeleteTarget] = useState<Entry | null>(null);

  const [openPath, setOpenPath] = useState<string | null>(null);
  const [openContent, setOpenContent] = useState("");
  const [isLoadingContent, setIsLoadingContent] = useState(false);
  const [isSaving, setIsSaving] = useState(false);

  const [goal, setGoal] = useState("");
  const [isRunning, setIsRunning] = useState(false);
  // A real, ongoing history — like Chat's own message list, not a single "latest result" that
  // got replaced (and so visually vanished) the moment a second goal was sent. Real bug, caught
  // live: "setelah saya kirim chat ke 2, chat yang pertama tadi hilang."
  const [runs, setRuns] = useState<AgentRunDetailOut[]>([]);

  // "This Computer" starts with no folder picked — dir stays "." and the file browser stays
  // hidden until one is chosen from hostFolders, instead of dumping the entire real D:\ root
  // (every top-level folder, each with a delete button) the moment the mode is switched on.
  // Real bug the previous version had: that root dump is exactly what showed up live.
  const [hostFolders, setHostFolders] = useState<Entry[] | null>(null);
  const [isLoadingHostFolders, setIsLoadingHostFolders] = useState(false);

  // Pushes both the URL and local state together, from one explicit (root, dir) pair — every
  // place root/dir change (the root tabs, the folder Select, breadcrumb clicks, clicking into a
  // folder row) goes through this instead of pushing the URL by hand, so every session — visited
  // via the sidebar or reached by clicking around the page itself — ends up with the same,
  // matching URL to restore from on a later visit/refresh. root/dir themselves just follow along
  // on the next render (see the derivation above), no separate state update needed here.
  function navigateToSession(nextRoot: Root, nextDir: string) {
    router.replace(`/code?root=${nextRoot}&dir=${encodeURIComponent(nextDir)}`, { scroll: false });
  }

  useEffect(() => {
    // Restores *this specific session's* history (not every Code-page run ever) so switching
    // sessions — via the sidebar, the root tabs, or a folder pick — shows that session's own
    // turns, the same way opening a different Chat conversation shows only its own messages.
    // Every run was already saved server-side the whole time (visible via Agents' "View full run
    // history"); this page just never looked back at it before. Oldest first, matching a chat
    // feed's reading order.
    (async () => {
      try {
        const all = await listAgentRuns();
        const matching = all
          .filter((r) => {
            const parsed = parseCodeGoal(r.goal);
            return parsed !== null && parsed.root === root && parsed.dir === dir;
          })
          .slice(0, 20)
          .reverse();
        const details = await Promise.all(matching.map((r) => getAgentRunStatus(r.id)));
        setRuns(details);
      } catch {
        // Not worth surfacing — the page still works fine starting blank.
      }
    })();
  }, [root, dir]);

  async function loadEntries(nextRoot: Root, nextDir: string) {
    setIsLoading(true);
    try {
      setEntries(await listFiles(nextRoot, nextDir));
    } catch (err) {
      toast.error(err instanceof ApiError ? err.message : "Couldn't load files.");
    } finally {
      setIsLoading(false);
    }
  }

  useEffect(() => {
    // "This Computer" mode never renders a file list (goal-driven only — see the JSX below), so
    // there's nothing to fetch for it here.
    if (root !== "workspace") return;
    // eslint-disable-next-line react-hooks/set-state-in-effect
    void loadEntries(root, dir);
  }, [root, dir]);

  useEffect(() => {
    // Covers both switchRoot below and landing here directly on a "This Computer" session link
    // from the sidebar/URL — either way, the folder dropdown needs real data to show.
    if (root !== "host" || hostFolders !== null) return;
    (async () => {
      setIsLoadingHostFolders(true);
      try {
        const hostEntries = await listHostFiles(".");
        setHostFolders(hostEntries.filter((e) => e.is_dir));
      } catch (err) {
        toast.error(err instanceof ApiError ? err.message : "Couldn't load D:\\'s folders.");
      } finally {
        setIsLoadingHostFolders(false);
      }
    })();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [root]);

  function switchRoot(nextRoot: Root) {
    if (nextRoot === root) return;
    navigateToSession(nextRoot, ".");
    setOpenPath(null);
    // History stays — switching between Workspace and This Computer changes where the *next*
    // goal runs, same as cd'ing elsewhere doesn't erase your terminal scrollback.
  }

  async function handleUpload(file: File) {
    setIsUploading(true);
    try {
      const path = dir === "." ? file.name : `${dir}/${file.name}`;
      await uploadFile(root, path, file);
      await loadEntries(root, dir);
      toast.success(`"${file.name}" added.`);
    } catch (err) {
      toast.error(err instanceof ApiError ? err.message : `"${file.name}" failed to upload.`);
    } finally {
      setIsUploading(false);
    }
  }

  async function openFile(entry: Entry) {
    if (entry.is_dir) {
      navigateToSession(root, entry.path);
      return;
    }
    setOpenPath(entry.path);
    setIsLoadingContent(true);
    try {
      const file = await getFileContent(root, entry.path);
      setOpenContent(file.content);
    } catch (err) {
      toast.error(err instanceof ApiError ? err.message : "Couldn't open that file.");
      setOpenPath(null);
    } finally {
      setIsLoadingContent(false);
    }
  }

  async function saveOpenFile() {
    if (!openPath) return;
    setIsSaving(true);
    try {
      const blob = new Blob([openContent], { type: "text/plain" });
      const file = new File([blob], openPath.split("/").pop() ?? openPath);
      await uploadFile(root, openPath, file);
      toast.success(`"${openPath}" saved.`);
      await loadEntries(root, dir);
    } catch (err) {
      toast.error(err instanceof ApiError ? err.message : "Couldn't save that file.");
    } finally {
      setIsSaving(false);
    }
  }

  async function confirmDelete() {
    if (!deleteTarget) return;
    const target = deleteTarget;
    setDeleteTarget(null);
    try {
      await deleteFile(root, target.path);
      setEntries((prev) => prev.filter((e) => e.path !== target.path));
      if (openPath === target.path) setOpenPath(null);
      toast.success(`"${target.name}" deleted.`);
    } catch (err) {
      toast.error(err instanceof ApiError ? err.message : "Couldn't delete that file.");
    }
  }

  async function handleRunGoal(e: React.FormEvent) {
    e.preventDefault();
    const trimmed = goal.trim();
    if (!trimmed) return;
    setIsRunning(true);
    try {
      const started = await runAgent(buildCodeGoal(trimmed, dir, root));
      const detail = await getAgentRunStatus(started.id);
      setRuns((prev) => [...prev, detail]);
      setGoal("");
      // So a brand-new (root, dir) session shows up in the sidebar right away, not just after a
      // full page reload.
      void loadCodeSessions();
      // The goal may have written/deleted files in the folder currently open — reflect that.
      // (Workspace mode only; "This Computer" mode never shows a file list to refresh.)
      if (root === "workspace") await loadEntries(root, dir);
    } catch (err) {
      toast.error(err instanceof ApiError ? err.message : "That run failed to start.");
    } finally {
      setIsRunning(false);
    }
  }

  const breadcrumbs = dir === "." ? [] : dir.split("/");
  const rootLabel = root === "workspace" ? "workspace" : "This Computer";

  return (
    <div className="flex flex-1 flex-col overflow-hidden">
      <header className="flex h-12 shrink-0 items-center justify-between border-b border-border px-4">
        <div className="flex items-center gap-3">
          <h1 className="text-sm font-medium">Code</h1>
          <div className="flex rounded-md border border-border p-0.5">
            {(["workspace", "host"] as const).map((r) => (
              <button
                key={r}
                type="button"
                onClick={() => switchRoot(r)}
                className={cn(
                  "rounded-[5px] px-2 py-1 text-xs font-medium",
                  root === r
                    ? "bg-secondary text-foreground"
                    : "text-muted-foreground hover:text-foreground",
                )}
              >
                {r === "workspace" ? "Workspace" : "This Computer (D:\\)"}
              </button>
            ))}
          </div>
          {root === "host" && (
            <Select
              value={dir === "." ? undefined : dir}
              onValueChange={(value) => navigateToSession(root, value)}
              disabled={isLoadingHostFolders}
            >
              <SelectTrigger className="h-7 w-52">
                <SelectValue
                  placeholder={isLoadingHostFolders ? "Loading folders…" : "Pick a folder in D:\\"}
                />
              </SelectTrigger>
              <SelectContent>
                {hostFolders?.map((f) => (
                  <SelectItem key={f.path} value={f.path}>
                    {f.name}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          )}
        </div>
        {root === "workspace" && (
          <div>
            <input
              ref={fileInputRef}
              type="file"
              className="hidden"
              onChange={(e) => {
                const f = e.target.files?.[0];
                if (f) void handleUpload(f);
                e.target.value = "";
              }}
            />
            <Button size="sm" onClick={() => fileInputRef.current?.click()} disabled={isUploading}>
              {isUploading ? <Loader2 className="size-3.5 animate-spin" /> : <Upload className="size-3.5" />}
              Upload
            </Button>
          </div>
        )}
      </header>

      <div className="scrollbar-thin flex-1 overflow-y-auto px-4 py-6">
        <div className="mx-auto flex w-full max-w-3xl flex-col gap-6">
          {root === "host" && (
            <div className="flex items-start gap-2 rounded-lg border border-destructive/30 bg-destructive/5 p-3 text-xs text-destructive">
              <TriangleAlert className="mt-0.5 size-3.5 shrink-0" />
              <p>
                <strong>Real access, no sandbox.</strong> The AI can read, overwrite, or delete any
                file under D:\, and run any command with full network access — no approval step, no
                isolation. Requires the <code>host-runner</code> service running locally (see{" "}
                <code>services/host-runner/README.md</code>).
              </p>
            </div>
          )}

          {runs.map((r) => (
            <RunEntry key={r.id} run={r} />
          ))}

          {/* "This Computer" mode is goal-driven only, deliberately — the AI already has
              host.list_files/host.read_file to look around when a goal needs it; a manual file
              browser here (every real file under the picked folder, each with a delete button)
              was exactly what didn't need to be shown, per direct feedback live. Workspace mode
              keeps its full browser — that's the safe, isolated sandbox, browsing it is fine. */}
          {root === "workspace" && (
            <>
              <div className="flex items-center gap-1 text-xs text-muted-foreground">
                <button type="button" onClick={() => navigateToSession(root, ".")} className="hover:text-foreground">
                  {rootLabel}
                </button>
                {breadcrumbs.map((segment, i) => {
                  const path = breadcrumbs.slice(0, i + 1).join("/");
                  return (
                    <span key={path} className="flex items-center gap-1">
                      <span>/</span>
                      <button type="button" onClick={() => navigateToSession(root, path)} className="hover:text-foreground">
                        {segment}
                      </button>
                    </span>
                  );
                })}
              </div>

              <div className="flex flex-col gap-2">
                {isLoading ? (
                  <div className="flex flex-col gap-2">
                    {Array.from({ length: 3 }).map((_, i) => (
                      <Skeleton key={i} className="h-14 w-full rounded-lg" />
                    ))}
                  </div>
                ) : entries.length === 0 ? (
                  <div className="flex flex-col items-center gap-2 rounded-xl border border-dashed border-border p-8 text-center">
                    <Code2 className="size-6 text-muted-foreground" />
                    <p className="text-sm text-muted-foreground">No files yet. Upload one to get started.</p>
                  </div>
                ) : (
                  entries.map((entry) => (
                    <div
                      key={entry.path}
                      className="flex items-center gap-3 rounded-lg border border-border p-3"
                    >
                      <button
                        type="button"
                        onClick={() => void openFile(entry)}
                        className="flex min-w-0 flex-1 items-center gap-3 text-left"
                      >
                        {entry.is_dir ? (
                          <Folder className="size-4 shrink-0 text-muted-foreground" />
                        ) : (
                          <FileIcon className="size-4 shrink-0 text-muted-foreground" />
                        )}
                        <div className="min-w-0 flex-1">
                          <p className="truncate text-sm font-medium">{entry.name}</p>
                          {!entry.is_dir && entry.size_bytes != null && (
                            <p className="text-xs text-muted-foreground">{formatBytes(entry.size_bytes)}</p>
                          )}
                        </div>
                      </button>
                      <Button
                        variant="ghost"
                        size="icon-sm"
                        aria-label={`Delete ${entry.name}`}
                        onClick={() => setDeleteTarget(entry)}
                      >
                        <Trash2 className="size-3.5" />
                      </Button>
                    </div>
                  ))
                )}
              </div>
            </>
          )}

          {openPath && (
            <div className="flex flex-col gap-2 rounded-lg border border-border p-3">
              <div className="flex items-center justify-between">
                <p className="text-sm font-medium">{openPath}</p>
                <div className="flex items-center gap-1">
                  <Button size="sm" onClick={() => void saveOpenFile()} disabled={isSaving || isLoadingContent}>
                    {isSaving ? <Loader2 className="size-3.5 animate-spin" /> : <Save className="size-3.5" />}
                    Save
                  </Button>
                  <Button variant="ghost" size="icon-sm" aria-label="Close" onClick={() => setOpenPath(null)}>
                    <X className="size-3.5" />
                  </Button>
                </div>
              </div>
              {isLoadingContent ? (
                <Skeleton className="h-48 w-full rounded-lg" />
              ) : (
                <Textarea
                  value={openContent}
                  onChange={(e) => setOpenContent(e.target.value)}
                  className="min-h-48 font-mono text-xs"
                  spellCheck={false}
                />
              )}
            </div>
          )}
        </div>
      </div>

      <form
        onSubmit={handleRunGoal}
        className="mx-auto flex w-full max-w-3xl shrink-0 flex-col gap-2 border-t border-border bg-background px-4 pt-3 pb-4"
      >
        <label htmlFor="code-goal" className="text-xs font-medium text-muted-foreground">
          What should the AI do in{" "}
          <span className="font-mono text-foreground">{dir === "." ? rootLabel : dir}</span>?
        </label>
        <Textarea
          id="code-goal"
          value={goal}
          onChange={(e) => setGoal(e.target.value)}
          placeholder="e.g. Read app.py, fix the bug where it crashes on empty input, then run the tests."
          rows={3}
          disabled={isRunning || (root === "host" && dir === ".")}
        />
        <div className="flex items-center justify-between gap-3">
          <p className="text-xs text-muted-foreground">
            {root === "host" && dir === "."
              ? "Pick a folder above first."
              : isRunning
                ? "Running — this can take up to two minutes."
                : "Runs immediately, no approval step — reads, writes, and executes for real."}
          </p>
          <Button
            type="submit"
            size="sm"
            disabled={isRunning || !goal.trim() || (root === "host" && dir === ".")}
            className="shrink-0"
          >
            {isRunning ? <Loader2 className="size-3.5 animate-spin" /> : <Bot className="size-3.5" />}
            Run
          </Button>
        </div>
      </form>

      <AlertDialog open={!!deleteTarget} onOpenChange={(open) => !open && setDeleteTarget(null)}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>Delete this file?</AlertDialogTitle>
            <AlertDialogDescription>
              &ldquo;{deleteTarget?.name}&rdquo; will be permanently deleted. This can&apos;t be undone.
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>Cancel</AlertDialogCancel>
            <AlertDialogAction className="bg-destructive text-white hover:bg-destructive/90" onClick={confirmDelete}>
              Delete
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </div>
  );
}

// One chat-style turn: the plain instruction as a "you said" bubble, the run's steps/result
// underneath — like a real chat message, not a bordered "Result" card repeating the same
// "View full run history" link on every single entry (declutter, per direct feedback live: once
// this became a real scrolling feed, that per-entry chrome stopped earning its place).
function RunEntry({ run }: { run: AgentRunDetailOut }) {
  return (
    <div className="flex flex-col gap-2">
      <div className="ml-auto max-w-[85%] rounded-xl bg-primary px-3.5 py-2 text-sm text-primary-foreground">
        {parseCodeGoal(run.goal)?.instruction ?? run.goal}
      </div>
      <div className="flex flex-col gap-2">
        {run.steps.map((step) => (
          <StepView key={`${step.step_number}-${step.type}`} step={step} />
        ))}
        {run.status === "waiting_approval" && (
          <p className="rounded-lg border border-destructive/30 bg-destructive/5 p-2.5 text-xs text-destructive">
            Paused waiting on approval for a tool call — open{" "}
            <Link href="/agents" className="underline underline-offset-2">
              Agents
            </Link>{" "}
            to approve or reject it.
          </p>
        )}
        {run.status === "failed" && run.error_message && (
          <p className="rounded-lg border border-destructive/30 bg-destructive/5 p-2.5 text-xs text-destructive">
            {run.error_message}
          </p>
        )}
      </div>
    </div>
  );
}

