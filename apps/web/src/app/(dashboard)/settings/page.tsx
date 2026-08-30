"use client";

import { Monitor, Moon, Sun } from "lucide-react";
import { useTheme } from "next-themes";
import { useEffect, useState } from "react";
import { toast } from "sonner";

import { Skeleton } from "@/components/ui/skeleton";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
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
  (s) => s !== "Appearance" && s !== "Account" && s !== "Usage",
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
