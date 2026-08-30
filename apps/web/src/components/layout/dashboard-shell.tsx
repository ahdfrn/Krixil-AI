"use client";

import { useRouter } from "next/navigation";
import { useEffect } from "react";

import { CommandMenu } from "@/components/layout/command-menu";
import { MobileSidebar } from "@/components/layout/mobile-sidebar";
import { Sidebar } from "@/components/layout/sidebar";
import { TopBar } from "@/components/layout/top-bar";
import { useAuthStore } from "@/stores/auth-store";
import { useChatStore } from "@/stores/chat-store";

export function DashboardShell({ children }: { children: React.ReactNode }) {
  const router = useRouter();
  const hasHydrated = useAuthStore((s) => s.hasHydrated);
  const isAuthenticated = useAuthStore((s) => s.isAuthenticated());
  const loadConversations = useChatStore((s) => s.loadConversations);
  const resetChatState = useChatStore((s) => s.resetChatState);

  useEffect(() => {
    if (!hasHydrated) return;
    if (!isAuthenticated) {
      // Clears any previous session's in-memory data (conversations, messages) so it can't
      // briefly reappear — e.g. in the command menu, which has no loading gate of its own — if a
      // different tenant logs in on the same tab before the next fetch lands. See web-phase5.md.
      resetChatState();
      router.replace("/login");
      return;
    }
    loadConversations();
    // loadConversations is a stable Zustand action reference; hasHydrated/isAuthenticated gate
    // when this is allowed to run at all.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [hasHydrated, isAuthenticated, router]);

  if (!hasHydrated || !isAuthenticated) return null;

  return (
    <div className="flex h-dvh flex-col overflow-hidden">
      <TopBar />
      <div className="flex flex-1 overflow-hidden">
        <Sidebar />
        <main className="flex min-w-0 flex-1 flex-col overflow-hidden">{children}</main>
      </div>
      <MobileSidebar />
      <CommandMenu />
    </div>
  );
}
