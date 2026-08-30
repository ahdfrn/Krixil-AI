"use client";

import { Archive, MoreVertical, Pencil, Pin, Trash2 } from "lucide-react";
import { useRouter } from "next/navigation";
import { useState } from "react";
import { toast } from "sonner";

import { ModelSelector } from "@/components/chat/model-selector";
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from "@/components/ui/alert-dialog";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { Input } from "@/components/ui/input";
import { useChatStore } from "@/stores/chat-store";
import type { Conversation } from "@/types/chat";

export function ChatHeader({ conversation }: { conversation: Conversation }) {
  const router = useRouter();
  const renameConversation = useChatStore((s) => s.renameConversation);
  const deleteConversation = useChatStore((s) => s.deleteConversation);

  const [isRenaming, setIsRenaming] = useState(false);
  const [draftTitle, setDraftTitle] = useState(conversation.title);
  const [confirmDeleteOpen, setConfirmDeleteOpen] = useState(false);

  function commitRename() {
    const title = draftTitle.trim();
    if (title && title !== conversation.title) void renameConversation(conversation.id, title);
    setIsRenaming(false);
  }

  return (
    <header className="flex h-12 shrink-0 items-center gap-2 border-b border-border px-4">
      {isRenaming ? (
        <Input
          autoFocus
          value={draftTitle}
          onChange={(e) => setDraftTitle(e.target.value)}
          onBlur={commitRename}
          onKeyDown={(e) => {
            if (e.key === "Enter") commitRename();
            if (e.key === "Escape") {
              setDraftTitle(conversation.title);
              setIsRenaming(false);
            }
          }}
          className="h-8 max-w-xs text-sm"
        />
      ) : (
        <h1 className="truncate text-sm font-medium">{conversation.title}</h1>
      )}

      <div className="ml-auto flex items-center gap-1">
        <ModelSelector
          value={conversation.model}
          onChange={() => toast.info("This is Krixil's only available model right now — more will show up here as they're added.")}
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
            <DropdownMenuItem onSelect={() => setIsRenaming(true)}>
              <Pencil /> Rename
            </DropdownMenuItem>
            <DropdownMenuItem onSelect={() => toast.info("Pinning conversations isn't available yet.")}>
              <Pin /> Pin
            </DropdownMenuItem>
            <DropdownMenuItem onSelect={() => toast.info("Archiving conversations isn't available yet.")}>
              <Archive /> Archive
            </DropdownMenuItem>
            <DropdownMenuItem variant="destructive" onSelect={() => setConfirmDeleteOpen(true)}>
              <Trash2 /> Delete
            </DropdownMenuItem>
          </DropdownMenuContent>
        </DropdownMenu>
      </div>

      <AlertDialog open={confirmDeleteOpen} onOpenChange={setConfirmDeleteOpen}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>Delete this conversation?</AlertDialogTitle>
            <AlertDialogDescription>
              &ldquo;{conversation.title}&rdquo; will be permanently deleted. This can&apos;t be
              undone.
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>Cancel</AlertDialogCancel>
            <AlertDialogAction
              className="bg-destructive text-white hover:bg-destructive/90"
              onClick={() => {
                void deleteConversation(conversation.id);
                setConfirmDeleteOpen(false);
                router.push("/chat");
              }}
            >
              Delete
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </header>
  );
}
