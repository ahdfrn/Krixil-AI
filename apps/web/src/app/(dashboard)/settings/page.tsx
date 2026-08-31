"use client";

import { Monitor, Moon, ShieldCheck, ShieldOff, Sun } from "lucide-react";
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
import { executeTool } from "@/lib/api/tools";
import { cn } from "@/lib/utils";
import { useAuthStore } from "@/stores/auth-store";

const SECTIONS = [
  "General",
  "Appearance",
  "Account",
  "AI Preferences",
  "Memory",
  "Privacy",
  "Security",
  "API Keys",
  "Usage",
  "Connected Apps",
] as const;

const PLACEHOLDER_SECTIONS = SECTIONS.filter(
  (s) => s !== "Appearance" && s !== "Account" && s !== "Usage" && s !== "Security",
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
