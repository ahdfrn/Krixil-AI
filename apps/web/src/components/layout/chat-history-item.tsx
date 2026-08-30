"use client";

import { Archive, MoreHorizontal, Pencil, Pin, PinOff, Trash2 } from "lucide-react";
import { useRouter } from "next/navigation";
import { useState } from "react";
import { toast } from "sonner";

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
import { cn } from "@/lib/utils";
import { useChatStore } from "@/stores/chat-store";
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
  const renameConversation = useChatStore((s) => s.renameConversation);
  const deleteConversation = useChatStore((s) => s.deleteConversation);
  const togglePin = useChatStore((s) => s.togglePin);
  const toggleArchive = useChatStore((s) => s.toggleArchive);

  const [isRenaming, setIsRenaming] = useState(false);
  const [draftTitle, setDraftTitle] = useState(conversation.title);
  const [confirmDeleteOpen, setConfirmDeleteOpen] = useState(false);

  function commitRename() {
    const title = draftTitle.trim();
    if (title && title !== conversation.title) {
      renameConversation(conversation.id, title);
    }
    setIsRenaming(false);
  }

  function handleDelete() {
    deleteConversation(conversation.id);
    setConfirmDeleteOpen(false);
    toast.success("Conversation deleted");
    if (active) router.push("/chat");
  }

  if (isRenaming) {
    return (
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
        className="h-8 text-sm"
      />
    );
  }

  return (
    <>
      <div
        className={cn(
          "group/item relative flex items-center rounded-md text-sm",
          active
            ? "bg-sidebar-accent text-sidebar-accent-foreground"
            : "hover:bg-sidebar-accent/60",
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
          {conversation.pinned && (
            <Pin className="size-3 shrink-0 text-muted-foreground" aria-hidden />
          )}
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
            <DropdownMenuItem onSelect={() => setIsRenaming(true)}>
              <Pencil /> Rename
            </DropdownMenuItem>
            <DropdownMenuItem onSelect={() => togglePin(conversation.id)}>
              {conversation.pinned ? (
                <>
                  <PinOff /> Unpin
                </>
              ) : (
                <>
                  <Pin /> Pin
                </>
              )}
            </DropdownMenuItem>
            <DropdownMenuItem onSelect={() => toggleArchive(conversation.id)}>
              <Archive /> {conversation.archived ? "Unarchive" : "Archive"}
            </DropdownMenuItem>
            <DropdownMenuItem
              variant="destructive"
              onSelect={() => setConfirmDeleteOpen(true)}
            >
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
              onClick={handleDelete}
            >
              Delete
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </>
  );
}
