"use client";

import {
  Brain,
  CheckCircle2,
  Cpu,
  Loader2,
  Monitor,
  Moon,
  ShieldCheck,
  ShieldOff,
  Sun,
  Trash2,
  XCircle,
} from "lucide-react";
import { useTheme } from "next-themes";
import QRCode from "qrcode";
import { useEffect, useState } from "react";
import { toast } from "sonner";

import {
  AlertDialog,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from "@/components/ui/alert-dialog";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Skeleton } from "@/components/ui/skeleton";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { confirm2FA, disable2FA, setup2FA, type TotpSetup } from "@/lib/api/auth";
import { ApiError } from "@/lib/api/client";
import {
  createMemory,
  deleteMemory,
  listMemories,
  setMemoryEnabled,
  type MemoryFact,
} from "@/lib/api/memory";
import { getFinetuneStatus, triggerFinetuneRun, type FinetuneRun, type FinetuneStatus } from "@/lib/api/finetune";
import { executeTool } from "@/lib/api/tools";
import { cn } from "@/lib/utils";
import { useAuthStore } from "@/stores/auth-store";

const SECTIONS = [
  "General",
  "Appearance",
  "Account",
  "AI Preferences",
  "Memory",
  "Fine-tuning",
  "Privacy",
  "Security",
  "API Keys",
  "Usage",
  "Connected Apps",
] as const;

const PLACEHOLDER_SECTIONS = SECTIONS.filter(
  (s) =>
    s !== "Appearance" &&
    s !== "Account" &&
    s !== "Usage" &&
    s !== "Security" &&
    s !== "Memory" &&
    s !== "Fine-tuning",
);

const THEME_OPTIONS = [
  { value: "light", label: "Light", icon: Sun },
  { value: "dark", label: "Dark", icon: Moon },
  { value: "system", label: "System", icon: Monitor },
] as const;

interface UsageSummary {
  period_days: number;
  request_count: number;
  prompt_tokens: number;
  completion_tokens: number;
  by_model: { model: string; request_count: number; prompt_tokens: number; completion_tokens: number }[];
}

export default function SettingsPage() {
  const { theme, setTheme } = useTheme();
  const [mounted, setMounted] = useState(false);
  const user = useAuthStore((s) => s.user);
  const tenant = useAuthStore((s) => s.tenant);

  const [usage, setUsage] = useState<UsageSummary | null>(null);
  const [isLoadingUsage, setIsLoadingUsage] = useState(true);

  async function loadUsage() {
    setIsLoadingUsage(true);
    try {
      const execution = await executeTool("usage.get_summary", { days: 30 });
      setUsage(execution.output as unknown as UsageSummary);
    } catch (err) {
      toast.error(err instanceof ApiError ? err.message : "Couldn't load usage.");
    } finally {
      setIsLoadingUsage(false);
    }
  }

  useEffect(() => {
    // Deferring theme-dependent styling until after mount avoids a hydration
    // mismatch: `theme` from next-themes is undefined on the server.
    // eslint-disable-next-line react-hooks/set-state-in-effect
    setMounted(true);
    // Fetch-on-mount, same pattern as the rest of this app's data loading (chat-store.ts).
    void loadUsage();
  }, []);

  return (
    <div className="flex flex-1 flex-col overflow-hidden">
      <header className="flex h-12 shrink-0 items-center border-b border-border px-4">
        <h1 className="text-sm font-medium">Settings</h1>
      </header>

      <div className="scrollbar-thin flex-1 overflow-y-auto px-4 py-6">
        <Tabs defaultValue="Appearance" className="mx-auto w-full max-w-3xl">
          <TabsList className="mb-6 flex h-auto flex-wrap justify-start gap-1 bg-transparent p-0">
            {SECTIONS.map((section) => (
              <TabsTrigger
                key={section}
                value={section}
                className="rounded-md border border-transparent data-[state=active]:border-border data-[state=active]:bg-secondary data-[state=active]:shadow-none"
              >
                {section}
              </TabsTrigger>
            ))}
          </TabsList>

          <TabsContent value="Appearance" className="space-y-4">
            <div className="rounded-xl border border-border p-4">
              <h2 className="text-sm font-medium">Theme</h2>
              <p className="mt-1 text-xs text-muted-foreground">
                Choose how Krixil AI looks on this device.
              </p>
              <div className="mt-4 grid grid-cols-3 gap-2">
                {THEME_OPTIONS.map((option) => (
                  <button
                    key={option.value}
                    type="button"
                    onClick={() => setTheme(option.value)}
                    className={cn(
                      "flex flex-col items-center gap-2 rounded-lg border border-border py-4 text-sm hover:bg-accent",
                      mounted && theme === option.value && "border-primary bg-accent",
                    )}
                  >
                    <option.icon className="size-4" />
                    {option.label}
                  </button>
                ))}
              </div>
            </div>
          </TabsContent>

          <TabsContent value="Account" className="space-y-4">
            <div className="rounded-xl border border-border p-4">
              <h2 className="text-sm font-medium">Account</h2>
              <p className="mt-1 text-xs text-muted-foreground">Read-only for now — there&apos;s no way to edit this yet.</p>
              <dl className="mt-4 grid grid-cols-[auto_1fr] gap-x-4 gap-y-2 text-sm">
                <dt className="text-muted-foreground">Email</dt>
                <dd>{user?.email}</dd>
                <dt className="text-muted-foreground">Workspace</dt>
                <dd>{tenant?.name}</dd>
                <dt className="text-muted-foreground">Workspace slug</dt>
                <dd className="font-mono text-xs">{tenant?.slug}</dd>
                <dt className="text-muted-foreground">Role</dt>
                <dd className="capitalize">{user?.role}</dd>
                <dt className="text-muted-foreground">Member since</dt>
                <dd>{user ? new Date(user.created_at).toLocaleDateString() : ""}</dd>
              </dl>
            </div>
          </TabsContent>

          <TabsContent value="Security" className="space-y-4">
            <SecurityTab />
          </TabsContent>

          <TabsContent value="Memory" className="space-y-4">
            <MemoryTab />
          </TabsContent>

          <TabsContent value="Fine-tuning" className="space-y-4">
            <FinetuneTab />
          </TabsContent>

          <TabsContent value="Usage" className="space-y-4">
            <div className="rounded-xl border border-border p-4">
              <h2 className="text-sm font-medium">Usage — last 30 days</h2>
              {isLoadingUsage ? (
                <div className="mt-4 grid grid-cols-3 gap-2">
                  {Array.from({ length: 3 }).map((_, i) => (
                    <Skeleton key={i} className="h-16 w-full rounded-lg" />
                  ))}
                </div>
              ) : usage ? (
                <>
                  <div className="mt-4 grid grid-cols-3 gap-2">
                    <UsageStat label="Requests" value={usage.request_count} />
                    <UsageStat label="Prompt tokens" value={usage.prompt_tokens} />
                    <UsageStat label="Completion tokens" value={usage.completion_tokens} />
                  </div>
                  {usage.by_model.length > 0 && (
                    <div className="mt-4 flex flex-col gap-1.5 border-t border-border pt-4 text-xs">
                      {usage.by_model.map((m) => (
                        <div key={m.model} className="flex justify-between text-muted-foreground">
                          <span className="text-foreground">{m.model}</span>
                          <span>
                            {m.request_count} requests · {m.prompt_tokens + m.completion_tokens} tokens
                          </span>
                        </div>
                      ))}
                    </div>
                  )}
                </>
              ) : (
                <p className="mt-2 text-xs text-muted-foreground">Couldn&apos;t load usage.</p>
              )}
            </div>
          </TabsContent>

          {PLACEHOLDER_SECTIONS.map((section) => (
            <TabsContent key={section} value={section}>
              <div className="rounded-xl border border-dashed border-border p-8 text-center">
                <p className="text-sm font-medium">{section}</p>
                <p className="mt-1 text-xs text-muted-foreground">
                  This section is UI-only for now — wired to real settings in a later phase.
                </p>
              </div>
            </TabsContent>
          ))}
        </Tabs>
      </div>
    </div>
  );
}

function UsageStat({ label, value }: { label: string; value: number }) {
  return (
    <div className="rounded-lg border border-border p-3">
      <p className="text-lg font-semibold">{value.toLocaleString()}</p>
      <p className="text-xs text-muted-foreground">{label}</p>
    </div>
  );
}

function SecurityTab() {
  const user = useAuthStore((s) => s.user);
  const updateUser = useAuthStore((s) => s.updateUser);

  const [setupData, setSetupData] = useState<TotpSetup | null>(null);
  const [qrDataUrl, setQrDataUrl] = useState<string | null>(null);
  const [confirmCode, setConfirmCode] = useState("");
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [disableOpen, setDisableOpen] = useState(false);
  const [disableCode, setDisableCode] = useState("");

  useEffect(() => {
    // Nothing renders qrDataUrl while setupData is null, so there's no need to clear it eagerly
    // here — the next setup attempt overwrites it before it could ever be shown stale.
    if (!setupData) return;
    let cancelled = false;
    QRCode.toDataURL(setupData.otpauth_url).then((url) => {
      if (!cancelled) setQrDataUrl(url);
    });
    return () => {
      cancelled = true;
    };
  }, [setupData]);

  async function handleStartSetup() {
    setIsSubmitting(true);
    try {
      setSetupData(await setup2FA());
    } catch (err) {
      toast.error(err instanceof ApiError ? err.message : "Couldn't start 2FA setup.");
    } finally {
      setIsSubmitting(false);
    }
  }

  async function handleConfirm(e: React.FormEvent) {
    e.preventDefault();
    setIsSubmitting(true);
    try {
      await confirm2FA(confirmCode.trim());
      updateUser({ totp_enabled: true });
      setSetupData(null);
      setConfirmCode("");
      toast.success("Two-factor authentication is on.");
    } catch (err) {
      toast.error(err instanceof ApiError ? err.message : "That code didn't work — try again.");
    } finally {
      setIsSubmitting(false);
    }
  }

  async function handleDisable(e: React.FormEvent) {
    e.preventDefault();
    setIsSubmitting(true);
    try {
      await disable2FA(disableCode.trim());
      updateUser({ totp_enabled: false });
      setDisableOpen(false);
      setDisableCode("");
      toast.success("Two-factor authentication is off.");
    } catch (err) {
      toast.error(err instanceof ApiError ? err.message : "That code didn't work — try again.");
    } finally {
      setIsSubmitting(false);
    }
  }

  return (
    <div className="rounded-xl border border-border p-4">
      <h2 className="text-sm font-medium">Two-factor authentication</h2>
      <p className="mt-1 text-xs text-muted-foreground">
        Require a code from an authenticator app (Google Authenticator, Authy, 1Password, etc.) in
        addition to your password when logging in.
      </p>

      {!setupData && (
        <div className="mt-4 flex items-center gap-3 rounded-lg border border-border p-3">
          {user?.totp_enabled ? (
            <ShieldCheck className="size-5 shrink-0 text-primary" />
          ) : (
            <ShieldOff className="size-5 shrink-0 text-muted-foreground" />
          )}
          <div className="flex-1">
            <p className="text-sm font-medium">
              {user?.totp_enabled ? "Enabled" : "Not enabled"}
            </p>
            <p className="text-xs text-muted-foreground">
              {user?.totp_enabled
                ? "Your account requires a code at login."
                : "Your account only requires a password at login."}
            </p>
          </div>
          {user?.totp_enabled ? (
            <Button size="sm" variant="destructive" onClick={() => setDisableOpen(true)}>
              Disable
            </Button>
          ) : (
            <Button size="sm" onClick={handleStartSetup} disabled={isSubmitting}>
              Enable 2FA
            </Button>
          )}
        </div>
      )}

      {setupData && (
        <div className="mt-4 flex flex-col gap-4 rounded-lg border border-border p-4">
          <div className="flex flex-col items-center gap-3 sm:flex-row sm:items-start">
            {qrDataUrl && (
              // Locally-generated data URL, not a remote image — next/image's optimizer doesn't apply.
              // eslint-disable-next-line @next/next/no-img-element
              <img
                src={qrDataUrl}
                alt="Scan this QR code with your authenticator app"
                className="size-40 shrink-0 rounded-lg border border-border bg-white p-2"
              />
            )}
            <div className="flex min-w-0 flex-col gap-1">
              <p className="text-xs text-muted-foreground">
                Scan with your authenticator app, or enter this code manually:
              </p>
              <code className="break-all rounded-md bg-secondary px-2 py-1 text-xs">
                {setupData.secret}
              </code>
            </div>
          </div>

          <form onSubmit={handleConfirm} className="flex items-end gap-2">
            <div className="flex flex-1 flex-col gap-1.5">
              <Label htmlFor="totp-confirm" className="text-xs">
                Enter the 6-digit code to confirm
              </Label>
              <Input
                id="totp-confirm"
                inputMode="numeric"
                maxLength={6}
                value={confirmCode}
                onChange={(e) => setConfirmCode(e.target.value)}
                placeholder="123456"
                required
              />
            </div>
            <Button type="submit" size="sm" disabled={isSubmitting}>
              Confirm
            </Button>
            <Button
              type="button"
              size="sm"
              variant="ghost"
              onClick={() => {
                setSetupData(null);
                setConfirmCode("");
              }}
            >
              Cancel
            </Button>
          </form>
        </div>
      )}

      <AlertDialog open={disableOpen} onOpenChange={setDisableOpen}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>Disable two-factor authentication?</AlertDialogTitle>
            <AlertDialogDescription>
              Enter a current code from your authenticator app to confirm.
            </AlertDialogDescription>
          </AlertDialogHeader>
          <form onSubmit={handleDisable} className="flex flex-col gap-3">
            <Input
              inputMode="numeric"
              maxLength={6}
              value={disableCode}
              onChange={(e) => setDisableCode(e.target.value)}
              placeholder="123456"
              autoFocus
              required
            />
            <AlertDialogFooter>
              <AlertDialogCancel type="button">Cancel</AlertDialogCancel>
              {/* Not AlertDialogAction: it auto-closes on click regardless of outcome, but this
                  needs to stay open on a wrong code so the user can retry — handleDisable closes
                  it explicitly, only on success. */}
              <Button type="submit" variant="destructive" disabled={isSubmitting}>
                Disable
              </Button>
            </AlertDialogFooter>
          </form>
        </AlertDialogContent>
      </AlertDialog>
    </div>
  );
}

function MemoryTab() {
  const user = useAuthStore((s) => s.user);
  const updateUser = useAuthStore((s) => s.updateUser);

  const [memories, setMemories] = useState<MemoryFact[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [newFact, setNewFact] = useState("");
  const [isSubmitting, setIsSubmitting] = useState(false);

  async function loadMemories() {
    setIsLoading(true);
    try {
      setMemories(await listMemories());
    } catch (err) {
      toast.error(err instanceof ApiError ? err.message : "Couldn't load what Krixil remembers.");
    } finally {
      setIsLoading(false);
    }
  }

  useEffect(() => {
    // Fetch-on-mount, same pattern as the rest of this app's data loading (chat-store.ts).
    // eslint-disable-next-line react-hooks/set-state-in-effect
    void loadMemories();
  }, []);

  async function handleToggle() {
    const next = !user?.memory_enabled;
    try {
      const result = await setMemoryEnabled(next);
      updateUser({ memory_enabled: result.memory_enabled });
      toast.success(result.memory_enabled ? "Memory is on." : "Memory is off.");
    } catch (err) {
      toast.error(err instanceof ApiError ? err.message : "Couldn't change that.");
    }
  }

  async function handleAdd(e: React.FormEvent) {
    e.preventDefault();
    const content = newFact.trim();
    if (!content) return;
    setIsSubmitting(true);
    try {
      const memory = await createMemory(content);
      setMemories((prev) => [memory, ...prev]);
      setNewFact("");
    } catch (err) {
      toast.error(err instanceof ApiError ? err.message : "Couldn't save that.");
    } finally {
      setIsSubmitting(false);
    }
  }

  async function handleDelete(id: string) {
    const previous = memories;
    setMemories((prev) => prev.filter((m) => m.id !== id));
    try {
      await deleteMemory(id);
    } catch (err) {
      setMemories(previous);
      toast.error(err instanceof ApiError ? err.message : "Couldn't remove that.");
    }
  }

  return (
    <div className="flex flex-col gap-4">
      <div className="rounded-xl border border-border p-4">
        <h2 className="text-sm font-medium">Long-term memory</h2>
        <p className="mt-1 text-xs text-muted-foreground">
          When on, Krixil picks up durable facts from your conversations (like your name or
          ongoing projects) and remembers them in future conversations too — not just within one
          chat. Conversations worth remembering also become searchable in your Knowledge base, the
          same way an uploaded document would.
        </p>
        <div className="mt-4 flex items-center gap-3 rounded-lg border border-border p-3">
          <Brain
            className={cn(
              "size-5 shrink-0",
              user?.memory_enabled ? "text-primary" : "text-muted-foreground",
            )}
          />
          <div className="flex-1">
            <p className="text-sm font-medium">{user?.memory_enabled ? "On" : "Off"}</p>
            <p className="text-xs text-muted-foreground">
              {user?.memory_enabled
                ? "Krixil may remember things you share in chat."
                : "Krixil won't remember anything new, and won't use what it already knows."}
            </p>
          </div>
          <Button size="sm" variant={user?.memory_enabled ? "destructive" : "default"} onClick={handleToggle}>
            {user?.memory_enabled ? "Turn off" : "Turn on"}
          </Button>
        </div>
      </div>

      <div className="rounded-xl border border-border p-4">
        <h2 className="text-sm font-medium">What Krixil remembers</h2>
        <form onSubmit={handleAdd} className="mt-3 flex items-center gap-2">
          <Input
            value={newFact}
            onChange={(e) => setNewFact(e.target.value)}
            placeholder="Tell Krixil something to remember..."
            className="flex-1"
          />
          <Button type="submit" size="sm" disabled={isSubmitting || !newFact.trim()}>
            Add
          </Button>
        </form>

        <div className="mt-4 flex flex-col gap-2">
          {isLoading ? (
            Array.from({ length: 3 }).map((_, i) => <Skeleton key={i} className="h-10 w-full rounded-lg" />)
          ) : memories.length === 0 ? (
            <p className="text-xs text-muted-foreground">
              Nothing yet — Krixil hasn&apos;t picked up any durable facts from your conversations.
            </p>
          ) : (
            memories.map((memory) => (
              <div
                key={memory.id}
                className="flex items-start justify-between gap-3 rounded-lg border border-border p-3 text-sm"
              >
                <span className="min-w-0 break-words">{memory.content}</span>
                <button
                  type="button"
                  onClick={() => handleDelete(memory.id)}
                  aria-label="Forget this"
                  className="shrink-0 text-muted-foreground hover:text-destructive"
                >
                  <Trash2 className="size-4" />
                </button>
              </div>
            ))
          )}
        </div>
      </div>
    </div>
  );
}

const RUN_STATUS_LABEL: Record<FinetuneRun["status"], string> = {
  requested: "Requested",
  running: "Running",
  promoted: "Promoted",
  discarded: "Discarded",
  failed: "Failed",
};

function FinetuneTab() {
  const [status, setStatus] = useState<FinetuneStatus | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [isTriggering, setIsTriggering] = useState(false);

  async function loadStatus() {
    setIsLoading(true);
    try {
      setStatus(await getFinetuneStatus());
    } catch (err) {
      toast.error(err instanceof ApiError ? err.message : "Couldn't load fine-tuning status.");
    } finally {
      setIsLoading(false);
    }
  }

  useEffect(() => {
    // Fetch-on-mount, same pattern as the rest of this app's data loading (chat-store.ts).
    // eslint-disable-next-line react-hooks/set-state-in-effect
    void loadStatus();
  }, []);

  async function handleRunNow() {
    setIsTriggering(true);
    try {
      await triggerFinetuneRun();
      toast.success("Requested — the training scheduler will pick this up on its next check.");
      await loadStatus();
    } catch (err) {
      toast.error(err instanceof ApiError ? err.message : "Couldn't request a run.");
    } finally {
      setIsTriggering(false);
    }
  }

  const progress = status ? Math.min(100, (status.example_count / status.min_examples) * 100) : 0;

  return (
    <div className="flex flex-col gap-4">
      <div className="rounded-xl border border-border p-4">
        <h2 className="text-sm font-medium">Autonomous fine-tuning</h2>
        <p className="mt-1 text-xs text-muted-foreground">
          Once there&apos;s enough real conversation history, Krixil periodically fine-tunes its
          own model on it — evaluated against the current model first, and only kept if it doesn&apos;t
          perform worse. A kept model shows up as a new choice in the model dropdown; nothing is
          ever silently replaced.
        </p>

        {isLoading ? (
          <Skeleton className="mt-4 h-16 w-full rounded-lg" />
        ) : status ? (
          <div className="mt-4 flex flex-col gap-3 rounded-lg border border-border p-3">
            <div className="flex items-center justify-between text-sm">
              <span className="font-medium">
                {status.example_count} of {status.min_examples} examples
              </span>
              <span className="text-xs text-muted-foreground">
                {status.ready ? "Ready to train" : "Not enough real usage yet"}
              </span>
            </div>
            <div className="h-1.5 w-full overflow-hidden rounded-full bg-secondary">
              <div
                className="h-full rounded-full bg-primary transition-all"
                style={{ width: `${progress}%` }}
              />
            </div>
            <div className="flex items-center justify-between">
              <p className="text-xs text-muted-foreground">
                {status.ready
                  ? "The next scheduled check will start a run automatically, or trigger one now."
                  : "Krixil keeps a small quality filter on real conversations, so more real usage is the only way to reach this."}
              </p>
              <Button size="sm" onClick={handleRunNow} disabled={isTriggering || !status.ready}>
                {isTriggering && <Loader2 className="size-3.5 animate-spin" />}
                Run now
              </Button>
            </div>
          </div>
        ) : (
          <p className="mt-4 text-xs text-muted-foreground">Couldn&apos;t load status.</p>
        )}
      </div>

      <div className="rounded-xl border border-border p-4">
        <h2 className="text-sm font-medium">Run history</h2>
        {isLoading ? (
          <div className="mt-3 flex flex-col gap-2">
            {Array.from({ length: 2 }).map((_, i) => (
              <Skeleton key={i} className="h-14 w-full rounded-lg" />
            ))}
          </div>
        ) : !status || status.runs.length === 0 ? (
          <p className="mt-2 text-xs text-muted-foreground">
            No runs yet — nothing has happened here on its own, and none have been requested
            manually.
          </p>
        ) : (
          <div className="mt-3 flex flex-col gap-2">
            {status.runs.map((run) => (
              <div key={run.id} className="rounded-lg border border-border p-3 text-sm">
                <div className="flex items-center gap-2">
                  {run.status === "promoted" && <CheckCircle2 className="size-4 shrink-0 text-primary" />}
                  {(run.status === "discarded" || run.status === "failed") && (
                    <XCircle className="size-4 shrink-0 text-muted-foreground" />
                  )}
                  {(run.status === "requested" || run.status === "running") && (
                    <Cpu className="size-4 shrink-0 text-muted-foreground" />
                  )}
                  <span className="font-medium">{RUN_STATUS_LABEL[run.status]}</span>
                  <span className="ml-auto text-xs text-muted-foreground">
                    {new Date(run.created_at).toLocaleString()}
                  </span>
                </div>
                <p className="mt-1 text-xs text-muted-foreground">
                  {run.example_count} examples
                  {run.eval_pass_count != null &&
                    ` · evaluation: ${run.eval_pass_count} passed, ${run.eval_fail_count} failed`}
                  {run.promoted_tag && ` · now available as "${run.promoted_tag}"`}
                </p>
                {run.detail && <p className="mt-1 text-xs text-muted-foreground">{run.detail}</p>}
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
