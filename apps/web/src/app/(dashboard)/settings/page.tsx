"use client";

import { Monitor, Moon, Sun } from "lucide-react";
import { useTheme } from "next-themes";
import { useEffect, useState } from "react";

import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { cn } from "@/lib/utils";

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

const THEME_OPTIONS = [
  { value: "light", label: "Light", icon: Sun },
  { value: "dark", label: "Dark", icon: Moon },
  { value: "system", label: "System", icon: Monitor },
] as const;

export default function SettingsPage() {
  const { theme, setTheme } = useTheme();
  const [mounted, setMounted] = useState(false);

  useEffect(() => {
    // Deferring theme-dependent styling until after mount avoids a hydration
    // mismatch: `theme` from next-themes is undefined on the server.
    // eslint-disable-next-line react-hooks/set-state-in-effect
    setMounted(true);
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

          {SECTIONS.filter((s) => s !== "Appearance").map((section) => (
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
