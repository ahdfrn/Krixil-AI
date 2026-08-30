"use client";

import { Keyboard, LogOut, Monitor, Moon, Settings, Sun, User } from "lucide-react";
import { useTheme } from "next-themes";
import Link from "next/link";
import { toast } from "sonner";

import { Avatar, AvatarFallback } from "@/components/ui/avatar";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuGroup,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuRadioGroup,
  DropdownMenuRadioItem,
  DropdownMenuSeparator,
  DropdownMenuSub,
  DropdownMenuSubContent,
  DropdownMenuSubTrigger,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";

// Phase 1: static mock user. Phase 2: comes from the authenticated session (see the master
// prompt's Authentication section) — nothing in this component's JSX needs to change, only
// where these two values are read from.
const MOCK_USER = { name: "Alex Rivera", email: "alex@krixil.dev" };

export function UserMenu({ compact = false }: { compact?: boolean }) {
  const { theme, setTheme } = useTheme();

  const initials = MOCK_USER.name
    .split(" ")
    .map((p) => p[0])
    .join("");

  return (
    <DropdownMenu>
      <DropdownMenuTrigger asChild>
        {compact ? (
          <button
            type="button"
            aria-label={`${MOCK_USER.name} — account menu`}
            className="flex size-9 items-center justify-center rounded-md hover:bg-sidebar-accent"
          >
            <Avatar className="size-6">
              <AvatarFallback className="bg-primary text-[10px] text-primary-foreground">
                {initials}
              </AvatarFallback>
            </Avatar>
          </button>
        ) : (
          <button
            type="button"
            className="flex w-full items-center gap-2 rounded-md px-2 py-1.5 text-left hover:bg-sidebar-accent/60"
          >
            <Avatar className="size-6">
              <AvatarFallback className="bg-primary text-[10px] text-primary-foreground">
                {initials}
              </AvatarFallback>
            </Avatar>
            <span className="truncate text-sm">{MOCK_USER.name}</span>
          </button>
        )}
      </DropdownMenuTrigger>
      <DropdownMenuContent align="start" className="w-56">
        <DropdownMenuLabel className="font-normal">
          <div className="flex flex-col">
            <span className="text-sm font-medium">{MOCK_USER.name}</span>
            <span className="text-xs text-muted-foreground">{MOCK_USER.email}</span>
          </div>
        </DropdownMenuLabel>
        <DropdownMenuSeparator />
        <DropdownMenuGroup>
          <DropdownMenuItem asChild>
            <Link href="/settings">
              <User /> Profile
            </Link>
          </DropdownMenuItem>
          <DropdownMenuItem asChild>
            <Link href="/settings">
              <Settings /> Settings
            </Link>
          </DropdownMenuItem>
        </DropdownMenuGroup>
        <DropdownMenuSeparator />
        <DropdownMenuSub>
          <DropdownMenuSubTrigger>
            {theme === "dark" ? <Moon /> : theme === "light" ? <Sun /> : <Monitor />}
            Theme
          </DropdownMenuSubTrigger>
          <DropdownMenuSubContent>
            <DropdownMenuRadioGroup value={theme} onValueChange={setTheme}>
              <DropdownMenuRadioItem value="light">
                <Sun /> Light
              </DropdownMenuRadioItem>
              <DropdownMenuRadioItem value="dark">
                <Moon /> Dark
              </DropdownMenuRadioItem>
              <DropdownMenuRadioItem value="system">
                <Monitor /> System
              </DropdownMenuRadioItem>
            </DropdownMenuRadioGroup>
          </DropdownMenuSubContent>
        </DropdownMenuSub>
        <DropdownMenuItem
          onSelect={() => toast.info("Keyboard shortcuts: Ctrl/Cmd+K, Ctrl/Cmd+Shift+O")}
        >
          <Keyboard /> Keyboard shortcuts
        </DropdownMenuItem>
        <DropdownMenuSeparator />
        <DropdownMenuItem
          variant="destructive"
          onSelect={() => toast("Sign out isn't wired up yet — no auth backend in this phase.")}
        >
          <LogOut /> Sign out
        </DropdownMenuItem>
      </DropdownMenuContent>
    </DropdownMenu>
  );
}
