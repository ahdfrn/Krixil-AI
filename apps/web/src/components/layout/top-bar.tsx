"use client";

import { Menu, Search, Sparkles } from "lucide-react";

import { Button } from "@/components/ui/button";
import { useUIStore } from "@/stores/ui-store";

export function TopBar() {
  const setMobileSidebarOpen = useUIStore((s) => s.setMobileSidebarOpen);
  const setCommandMenuOpen = useUIStore((s) => s.setCommandMenuOpen);

  return (
    <header className="flex h-12 shrink-0 items-center gap-2 border-b border-border px-2 md:justify-end md:border-b-0 md:px-3">
      <Button
        variant="ghost"
        size="icon"
        className="md:hidden"
        aria-label="Open menu"
        onClick={() => setMobileSidebarOpen(true)}
      >
        <Menu className="size-5" />
      </Button>

      <div className="flex items-center gap-1.5 md:hidden">
        <div className="flex size-6 items-center justify-center rounded-md bg-primary text-primary-foreground">
          <Sparkles className="size-3.5" />
        </div>
        <span className="text-sm font-semibold">Krixil AI</span>
      </div>

      <button
        type="button"
        onClick={() => setCommandMenuOpen(true)}
        className="ml-auto flex items-center gap-2 rounded-md border border-border bg-secondary/40 px-2.5 py-1.5 text-xs text-muted-foreground hover:bg-secondary"
      >
        <Search className="size-3.5" />
        <span className="hidden sm:inline">Search</span>
        <kbd className="hidden rounded border border-border bg-background px-1 font-mono text-[10px] sm:inline">
          ⌘K
        </kbd>
      </button>
    </header>
  );
}
