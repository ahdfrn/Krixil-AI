"use client";

import { Archive, MoreHorizontal, Pencil, Pin, Trash2 } from "lucide-react";
import { useRouter } from "next/navigation";
import { toast } from "sonner";

import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { cn } from "@/lib/utils";
import type { Conversation } from "@/types/chat";

export function ChatHistoryItem({
  conversation,
  active,
  onNavigate,
}: {
  conversation: Conversation;
  active: boolean;
  onNavigate?: () => void;
}) {
  const router = useRouter();

  return (
    <div
      className={cn(
        "group/item relative flex items-center rounded-md text-sm",
        active ? "bg-sidebar-accent text-sidebar-accent-foreground" : "hover:bg-sidebar-accent/60",
      )}
    >
      <a
        href={`/chat/${conversation.id}`}
        onClick={(e) => {
          e.preventDefault();
          router.push(`/chat/${conversation.id}`);
          onNavigate?.();
        }}
        className="flex min-w-0 flex-1 items-center gap-1.5 truncate px-2.5 py-1.5"
      >
        <span className="truncate">{conversation.title}</span>
      </a>

      <DropdownMenu>
        <DropdownMenuTrigger asChild>
          <button
            type="button"
            aria-label={`More actions for ${conversation.title}`}
            className="mr-1 flex size-6 shrink-0 items-center justify-center rounded opacity-0 hover:bg-sidebar-accent focus-visible:opacity-100 group-hover/item:opacity-100 data-[state=open]:opacity-100 data-[state=open]:bg-sidebar-accent"
          >
            <MoreHorizontal className="size-4" />
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
  );
}
