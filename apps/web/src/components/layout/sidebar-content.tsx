"use client";

import {
  BookOpen,
  Bot,
  Code2,
  FileText,
  HelpCircle,
  PanelLeftClose,
  Plus,
  Search,
  Settings,
  Sparkles,
  Wrench,
} from "lucide-react";
import Link from "next/link";
import { useParams, usePathname, useRouter } from "next/navigation";

import { ChatHistoryItem } from "@/components/layout/chat-history-item";
import { UserMenu } from "@/components/layout/user-menu";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { cn } from "@/lib/utils";
import { groupConversationsByDate } from "@/lib/utils/date-groups";
import { useChatStore } from "@/stores/chat-store";
import { useUIStore } from "@/stores/ui-store";

const WORKSPACE_ITEMS = [
  { href: "/knowledge", label: "Knowledge", icon: BookOpen },
  { href: "/agents", label: "Agents", icon: Bot },
  { href: "/tools", label: "Tools", icon: Wrench },
  { href: "/code", label: "Code", icon: Code2 },
  { href: "/files", label: "Files", icon: FileText },
];

export function SidebarContent({
  onNavigate,
  onCollapse,
}: {
  onNavigate?: () => void;
  onCollapse?: () => void;
}) {
  const router = useRouter();
  const pathname = usePathname();
  const params = useParams<{ conversationId?: string }>();

  const conversations = useChatStore((s) => s.conversations);
  const isLoading = useChatStore((s) => s.isLoadingConversations);
  const setCommandMenuOpen = useUIStore((s) => s.setCommandMenuOpen);

  const visible = conversations.filter((c) => !c.archived);
  const groups = groupConversationsByDate(visible);

  function handleNewChat() {
    router.push("/chat");
    onNavigate?.();
  }

  return (
    <div className="flex h-full min-w-0 flex-col">
      <div className="flex items-center gap-2 px-3 pt-3 pb-1">
        <div className="flex size-7 items-center justify-center rounded-md bg-primary text-primary-foreground">
          <Sparkles className="size-4" />
        </div>
        <span className="text-sm font-semibold tracking-tight">Krixil AI</span>
        {onCollapse && (
          <button
            type="button"
            aria-label="Collapse sidebar"
            onClick={onCollapse}
            className="ml-auto flex size-6 items-center justify-center rounded text-muted-foreground hover:bg-sidebar-accent hover:text-sidebar-accent-foreground"
          >
            <PanelLeftClose className="size-4" />
          </button>
        )}
      </div>

      <div className="flex flex-col gap-1 px-2 pt-3">
        <Button
          variant="secondary"
          className="justify-start gap-2 border border-sidebar-border/80"
          onClick={handleNewChat}
        >
          <Plus className="size-4" />
          New Chat
        </Button>
        <Button
          variant="ghost"
          className="justify-start gap-2 text-muted-foreground"
          onClick={() => setCommandMenuOpen(true)}
        >
          <Search className="size-4" />
          Search
        </Button>
      </div>

      <div className="scrollbar-thin mt-3 flex-1 overflow-y-auto px-2">
        <div className="px-1.5 pb-1 text-xs font-medium text-muted-foreground">Chats</div>
        {isLoading ? (
          <div className="flex flex-col gap-1.5 px-1.5 py-1">
            {Array.from({ length: 5 }).map((_, i) => (
              <Skeleton key={i} className="h-7 w-full" />
            ))}
          </div>
        ) : groups.length === 0 ? (
          <p className="px-2.5 py-2 text-xs text-muted-foreground">No conversations yet.</p>
        ) : (
          groups.map((group) => (
            <div key={group.label} className="mb-2">
              <div className="px-1.5 pt-2 pb-1 text-xs text-muted-foreground/70">
                {group.label}
              </div>
              <div className="flex flex-col gap-0.5">
                {group.conversations.map((conversation) => (
                  <ChatHistoryItem
                    key={conversation.id}
                    conversation={conversation}
                    active={params.conversationId === conversation.id}
                    onNavigate={onNavigate}
                  />
                ))}
              </div>
            </div>
          ))
        )}

        <div className="mt-4 px-1.5 pb-1 text-xs font-medium text-muted-foreground">
          Workspace
        </div>
        <nav className="flex flex-col gap-0.5 pb-2">
          {WORKSPACE_ITEMS.map((item) => {
            const active = pathname.startsWith(item.href);
            return (
              <Link
                key={item.href}
                href={item.href}
                onClick={onNavigate}
                className={cn(
                  "flex items-center gap-2 rounded-md px-2.5 py-1.5 text-sm",
                  active
                    ? "bg-sidebar-accent text-sidebar-accent-foreground"
                    : "text-sidebar-foreground/80 hover:bg-sidebar-accent/60",
                )}
              >
                <item.icon className="size-4" />
                {item.label}
              </Link>
            );
          })}
        </nav>
      </div>

      <div className="border-t border-sidebar-border px-2 py-2">
        <Link
          href="/settings"
          onClick={onNavigate}
          className={cn(
            "flex items-center gap-2 rounded-md px-2.5 py-1.5 text-sm",
            pathname.startsWith("/settings")
              ? "bg-sidebar-accent text-sidebar-accent-foreground"
              : "text-sidebar-foreground/80 hover:bg-sidebar-accent/60",
          )}
        >
          <Settings className="size-4" />
          Settings
        </Link>
        <Link
          href="/help"
          onClick={onNavigate}
          className={cn(
            "flex items-center gap-2 rounded-md px-2.5 py-1.5 text-sm",
            pathname.startsWith("/help")
              ? "bg-sidebar-accent text-sidebar-accent-foreground"
              : "text-sidebar-foreground/80 hover:bg-sidebar-accent/60",
          )}
        >
          <HelpCircle className="size-4" />
          Help
        </Link>
        <div className="mt-1 border-t border-sidebar-border pt-1">
          <UserMenu />
        </div>
      </div>
    </div>
  );
}
