"use client";

import { Archive, MoreVertical, Pencil, Pin, Trash2 } from "lucide-react";
import { toast } from "sonner";

import { ModelSelector } from "@/components/chat/model-selector";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import type { Conversation } from "@/types/chat";

export function ChatHeader({ conversation }: { conversation: Conversation }) {
  return (
    <header className="flex h-12 shrink-0 items-center gap-2 border-b border-border px-4">
      <h1 className="truncate text-sm font-medium">{conversation.title}</h1>

      <div className="ml-auto flex items-center gap-1">
        <ModelSelector
          value={conversation.model}
          onChange={() => toast.info("Krixil routes to a model automatically — manual selection isn't supported yet.")}
          size="sm"
        />

        <DropdownMenu>
          <DropdownMenuTrigger asChild>
            <button
              type="button"
              aria-label="Chat options"
              className="flex size-8 items-center justify-center rounded-md text-muted-foreground hover:bg-secondary hover:text-foreground"
            >
              <MoreVertical className="size-4" />
            </button>
          </DropdownMenuTrigger>
          <DropdownMenuContent align="end" className="w-44">
            <DropdownMenuItem onSelect={() => toast.info("Renaming conversations isn't available yet.")}>
              <Pencil /> Rename
            </DropdownMenuItem>
            <DropdownMenuItem onSelect={() => toast.info("Pinning conversations isn't available yet.")}>
              <Pin /> Pin
            </DropdownMenuItem>
            <DropdownMenuItem onSelect={() => toast.info("Archiving conversations isn't available yet.")}>
              <Archive /> Archive
            </DropdownMenuItem>
            <DropdownMenuItem
              variant="destructive"
              onSelect={() => toast.info("Deleting conversations isn't available yet.")}
            >
              <Trash2 /> Delete
            </DropdownMenuItem>
          </DropdownMenuContent>
        </DropdownMenu>
      </div>
    </header>
  );
}
