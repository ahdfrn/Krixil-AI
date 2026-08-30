"use client";

import { Check, Loader2, Wrench, X } from "lucide-react";
import { useEffect, useState } from "react";
import { toast } from "sonner";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Skeleton } from "@/components/ui/skeleton";
import { ApiError } from "@/lib/api/client";
import { listDocuments, type DocumentOut } from "@/lib/api/documents";
import {
  approveExecution,
  executeTool,
  listExecutions,
  listTools,
  rejectExecution,
  type RiskLevel,
  type ToolExecutionOut,
  type ToolOut,
} from "@/lib/api/tools";

const RISK_VARIANT: Record<RiskLevel, "secondary" | "outline" | "destructive"> = {
  low: "secondary",
  medium: "outline",
  high: "destructive",
  critical: "destructive",
};

const STATUS_LABEL: Record<ToolExecutionOut["status"], string> = {
  pending_approval: "Pending approval",
  running: "Running",
  completed: "Completed",
  failed: "Failed",
  rejected: "Rejected",
};

function summarizeOutput(toolName: string, output: Record<string, unknown> | null): string | null {
  if (!output) return null;
  if (toolName === "usage.get_summary") {
    return `${output.request_count} requests · ${output.prompt_tokens} prompt tokens · ${output.completion_tokens} completion tokens (last ${output.period_days} days)`;
  }
  if (toolName === "knowledge.search") {
    const results = output.results as unknown[] | undefined;
    return `${results?.length ?? 0} result${results?.length === 1 ? "" : "s"} found`;
  }
  if (toolName === "document.delete") {
    return `Deleted document ${output.document_id}`;
  }
  return JSON.stringify(output);
}

export default function ToolsPage() {
  const [tools, setTools] = useState<ToolOut[]>([]);
  const [executions, setExecutions] = useState<ToolExecutionOut[]>([]);
  const [documents, setDocuments] = useState<DocumentOut[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [pendingAction, setPendingAction] = useState<string | null>(null);

  async function loadAll() {
    setIsLoading(true);
    try {
      const [toolList, executionList, documentList] = await Promise.all([
        listTools(),
        listExecutions(),
        listDocuments(),
      ]);
      setTools(toolList);
      setExecutions(executionList);
      setDocuments(documentList);
    } catch (err) {
      toast.error(err instanceof ApiError ? err.message : "Couldn't load tools.");
    } finally {
      setIsLoading(false);
    }
  }

  useEffect(() => {
    // Fetch-on-mount, same pattern as the rest of this app's data loading (chat-store.ts).
    // eslint-disable-next-line react-hooks/set-state-in-effect
    void loadAll();
  }, []);

  async function runTool(name: string, input: Record<string, unknown>) {
    setPendingAction(name);
    try {
      const execution = await executeTool(name, input);
      setExecutions((prev) => [execution, ...prev]);
      if (execution.status === "pending_approval") {
        toast.info(`"${name}" needs approval before it runs — see the execution below.`);
      } else if (execution.status === "completed") {
        toast.success(`"${name}" completed.`);
      } else {
        toast.error(execution.error_message ?? `"${name}" failed.`);
      }
    } catch (err) {
      toast.error(err instanceof ApiError ? err.message : `"${name}" failed to run.`);
    } finally {
      setPendingAction(null);
    }
  }

  async function handleApprove(execution: ToolExecutionOut) {
    setPendingAction(execution.id);
    try {
      const updated = await approveExecution(execution.id);
      setExecutions((prev) => prev.map((e) => (e.id === updated.id ? updated : e)));
      if (updated.status === "completed") {
        toast.success(`"${updated.tool_name}" approved and ran successfully.`);
        if (updated.tool_name === "document.delete") void loadAll();
      } else {
        toast.error(updated.error_message ?? "Approved, but the tool failed to run.");
      }
    } catch (err) {
      toast.error(err instanceof ApiError ? err.message : "Couldn't approve that execution.");
    } finally {
      setPendingAction(null);
    }
  }

  async function handleReject(execution: ToolExecutionOut) {
    setPendingAction(execution.id);
    try {
      const updated = await rejectExecution(execution.id);
      setExecutions((prev) => prev.map((e) => (e.id === updated.id ? updated : e)));
      toast.info(`"${updated.tool_name}" rejected.`);
    } catch (err) {
      toast.error(err instanceof ApiError ? err.message : "Couldn't reject that execution.");
    } finally {
      setPendingAction(null);
    }
  }

  return (
    <div className="flex flex-1 flex-col overflow-hidden">
      <header className="flex h-12 shrink-0 items-center border-b border-border px-4">
        <h1 className="text-sm font-medium">Tools</h1>
      </header>

      <div className="scrollbar-thin flex-1 overflow-y-auto px-4 py-6">
        <div className="mx-auto flex w-full max-w-3xl flex-col gap-8">
          <div className="flex flex-col gap-3">
            <h2 className="text-xs font-medium text-muted-foreground">Available tools</h2>
            {isLoading ? (
              <div className="flex flex-col gap-2">
                {Array.from({ length: 3 }).map((_, i) => (
                  <Skeleton key={i} className="h-24 w-full rounded-xl" />
                ))}
              </div>
            ) : (
              tools.map((tool) => (
                <ToolCard
                  key={tool.name}
                  tool={tool}
                  documents={documents}
                  isRunning={pendingAction === tool.name}
                  onRun={(input) => runTool(tool.name, input)}
                />
              ))
            )}
          </div>

          <div className="flex flex-col gap-3">
            <h2 className="text-xs font-medium text-muted-foreground">Execution history</h2>
            {isLoading ? (
              <Skeleton className="h-20 w-full rounded-lg" />
            ) : executions.length === 0 ? (
              <div className="flex flex-col items-center gap-2 rounded-xl border border-dashed border-border p-8 text-center">
                <Wrench className="size-6 text-muted-foreground" />
                <p className="text-sm text-muted-foreground">No tool executions yet — run one above.</p>
              </div>
            ) : (
              executions.map((execution) => (
                <div key={execution.id} className="rounded-lg border border-border p-3 text-sm">
                  <div className="flex flex-wrap items-center gap-2">
                    <span className="font-medium">{execution.tool_name}</span>
                    <Badge variant={RISK_VARIANT[execution.risk_level]}>{execution.risk_level}</Badge>
                    <Badge variant="outline">{STATUS_LABEL[execution.status]}</Badge>
                    <span className="ml-auto text-xs text-muted-foreground">
                      {new Date(execution.created_at).toLocaleString()}
                    </span>
                  </div>

                  {execution.status === "pending_approval" && (
                    <div className="mt-2 flex items-center gap-2 border-t border-border pt-2">
                      <p className="flex-1 text-xs text-muted-foreground">
                        This is a {execution.risk_level}-risk action and needs approval before it runs.
                      </p>
                      <Button
                        size="sm"
                        variant="secondary"
                        disabled={pendingAction === execution.id}
                        onClick={() => handleApprove(execution)}
                      >
                        {pendingAction === execution.id ? (
                          <Loader2 className="size-3.5 animate-spin" />
                        ) : (
                          <Check className="size-3.5" />
                        )}
                        Approve
                      </Button>
                      <Button
                        size="sm"
                        variant="ghost"
                        disabled={pendingAction === execution.id}
                        onClick={() => handleReject(execution)}
                      >
                        <X className="size-3.5" />
                        Reject
                      </Button>
                    </div>
                  )}

                  {execution.status === "completed" && (
                    <p className="mt-2 border-t border-border pt-2 text-xs text-muted-foreground">
                      {summarizeOutput(execution.tool_name, execution.output)}
                    </p>
                  )}

                  {(execution.status === "failed" || execution.status === "rejected") && execution.error_message && (
                    <p className="mt-2 border-t border-border pt-2 text-xs text-destructive">
                      {execution.error_message}
                    </p>
                  )}
                </div>
              ))
            )}
          </div>
        </div>
      </div>
    </div>
  );
}

function ToolCard({
  tool,
  documents,
  isRunning,
  onRun,
}: {
  tool: ToolOut;
  documents: DocumentOut[];
  isRunning: boolean;
  onRun: (input: Record<string, unknown>) => void;
}) {
  return (
    <div className="rounded-xl border border-border p-4">
      <div className="flex items-center gap-2">
        <span className="text-sm font-medium">{tool.name}</span>
        <Badge variant={RISK_VARIANT[tool.risk_level]}>{tool.risk_level}</Badge>
      </div>
      <p className="mt-1 text-xs text-muted-foreground">{tool.description}</p>
      <div className="mt-3 border-t border-border pt-3">
        <ToolForm tool={tool} documents={documents} isRunning={isRunning} onRun={onRun} />
      </div>
    </div>
  );
}

// Hand-written per tool rather than a generic JSON-Schema form renderer — there are exactly 3
// tools with small, simple schemas, so a generic builder would be more code for no real payoff.
function ToolForm({
  tool,
  documents,
  isRunning,
  onRun,
}: {
  tool: ToolOut;
  documents: DocumentOut[];
  isRunning: boolean;
  onRun: (input: Record<string, unknown>) => void;
}) {
  const [query, setQuery] = useState("");
  const [days, setDays] = useState("30");
  const [documentId, setDocumentId] = useState("");

  if (tool.name === "knowledge.search") {
    return (
      <form
        className="flex gap-2"
        onSubmit={(e) => {
          e.preventDefault();
          if (query.trim()) onRun({ query: query.trim() });
        }}
      >
        <Input
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          placeholder="Search query..."
          className="flex-1"
        />
        <Button type="submit" size="sm" disabled={isRunning || !query.trim()}>
          {isRunning ? <Loader2 className="size-3.5 animate-spin" /> : "Run"}
        </Button>
      </form>
    );
  }

  if (tool.name === "usage.get_summary") {
    return (
      <form
        className="flex items-end gap-2"
        onSubmit={(e) => {
          e.preventDefault();
          const parsed = Number(days);
          if (parsed >= 1 && parsed <= 365) onRun({ days: parsed });
        }}
      >
        <div className="flex flex-col gap-1">
          <Label htmlFor="usage-days" className="text-xs">Days</Label>
          <Input
            id="usage-days"
            type="number"
            min={1}
            max={365}
            value={days}
            onChange={(e) => setDays(e.target.value)}
            className="w-24"
          />
        </div>
        <Button type="submit" size="sm" disabled={isRunning}>
          {isRunning ? <Loader2 className="size-3.5 animate-spin" /> : "Run"}
        </Button>
      </form>
    );
  }

  if (tool.name === "document.delete") {
    return (
      <form
        className="flex items-end gap-2"
        onSubmit={(e) => {
          e.preventDefault();
          if (documentId) onRun({ document_id: documentId });
        }}
      >
        <div className="flex min-w-0 flex-1 flex-col gap-1">
          <Label htmlFor="doc-select" className="text-xs">Document</Label>
          <select
            id="doc-select"
            value={documentId}
            onChange={(e) => setDocumentId(e.target.value)}
            className="h-8 w-full rounded-lg border border-input bg-transparent px-2.5 text-sm outline-none focus-visible:border-ring focus-visible:ring-3 focus-visible:ring-ring/50"
          >
            <option value="">Select a document...</option>
            {documents.map((doc) => (
              <option key={doc.id} value={doc.id}>
                {doc.filename}
              </option>
            ))}
          </select>
        </div>
        <Button type="submit" size="sm" variant="destructive" disabled={isRunning || !documentId}>
          {isRunning ? <Loader2 className="size-3.5 animate-spin" /> : "Run"}
        </Button>
      </form>
    );
  }

  return null;
}
