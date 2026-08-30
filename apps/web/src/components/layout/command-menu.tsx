"use client";

import { BookOpen, Bot, Monitor, Moon, Plus, Settings, Sun, Wrench } from "lucide-react";
import { useTheme } from "next-themes";
import { useRouter } from "next/navigation";
import { useEffect } from "react";

import {
  CommandDialog,
  CommandEmpty,
  CommandGroup,
  CommandInput,
  CommandItem,
  CommandList,
  CommandSeparator,
} from "@/components/ui/command";
import { useChatStore } from "@/stores/chat-store";
import { useUIStore } from "@/stores/ui-store";

export function CommandMenu() {
  const open = useUIStore((s) => s.commandMenuOpen);
  const setOpen = useUIStore((s) => s.setCommandMenuOpen);
  const conversations = useChatStore((s) => s.conversations);
  const router = useRouter();
  const { setTheme } = useTheme();

  useEffect(() => {
    function onKeyDown(e: KeyboardEvent) {
      const isK = e.key.toLowerCase() === "k" && (e.metaKey || e.ctrlKey);
      const isNewChat =
        e.key.toLowerCase() === "o" && (e.metaKey || e.ctrlKey) && e.shiftKey;
      if (isK) {
        e.preventDefault();
        setOpen(!open);
      }
      if (isNewChat) {
        e.preventDefault();
        setOpen(false);
        router.push("/chat");
      }
    }
    document.addEventListener("keydown", onKeyDown);
    return () => document.removeEventListener("keydown", onKeyDown);
  }, [open, router, setOpen]);

  function go(href: string) {
    setOpen(false);
    router.push(href);
  }

  return (
    <CommandDialog open={open} onOpenChange={setOpen}>
      <CommandInput placeholder="Search conversations or run a command..." />
      <CommandList>
        <CommandEmpty>No results found.</CommandEmpty>
        <CommandGroup heading="Actions">
          <CommandItem onSelect={() => go("/chat")}>
            <Plus /> New chat
          </CommandItem>
          <CommandItem onSelect={() => go("/knowledge")}>
            <BookOpen /> Open knowledge
          </CommandItem>
          <CommandItem onSelect={() => go("/agents")}>
            <Bot /> Open agents
          </CommandItem>
          <CommandItem onSelect={() => go("/tools")}>
            <Wrench /> Open tools
          </CommandItem>
          <CommandItem onSelect={() => go("/settings")}>
            <Settings /> Open settings
          </CommandItem>
        </CommandGroup>
        <CommandSeparator />
        <CommandGroup heading="Theme">
          <CommandItem onSelect={() => setTheme("light")}>
            <Sun /> Light
          </CommandItem>
          <CommandItem onSelect={() => setTheme("dark")}>
            <Moon /> Dark
          </CommandItem>
          <CommandItem onSelect={() => setTheme("system")}>
            <Monitor /> System
          </CommandItem>
        </CommandGroup>
        {conversations.length > 0 && (
          <>
            <CommandSeparator />
            <CommandGroup heading="Conversations">
              {conversations.map((c) => (
                <CommandItem key={c.id} onSelect={() => go(`/chat/${c.id}`)}>
                  {c.title}
                </CommandItem>
              ))}
            </CommandGroup>
          </>
        )}
      </CommandList>
    </CommandDialog>
  );
}
