"use client";

import { useEffect } from "react";

import { CommandMenu } from "@/components/layout/command-menu";
import { MobileSidebar } from "@/components/layout/mobile-sidebar";
import { Sidebar } from "@/components/layout/sidebar";
import { TopBar } from "@/components/layout/top-bar";
import { useChatStore } from "@/stores/chat-store";

export function DashboardShell({ children }: { children: React.ReactNode }) {
  const loadConversations = useChatStore((s) => s.loadConversations);

  useEffect(() => {
    loadConversations();
    // Runs once on mount — loadConversations is a stable Zustand action reference.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

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
