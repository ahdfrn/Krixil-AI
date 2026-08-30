"use client";

import { SidebarContent } from "@/components/layout/sidebar-content";
import { SidebarRail } from "@/components/layout/sidebar-rail";
import { cn } from "@/lib/utils";
import { useUIStore } from "@/stores/ui-store";

export function Sidebar() {
  const collapsed = useUIStore((s) => s.sidebarCollapsed);
  const toggleSidebarCollapsed = useUIStore((s) => s.toggleSidebarCollapsed);

  return (
    <aside
      className={cn(
        "hidden shrink-0 border-r border-sidebar-border bg-sidebar transition-[width] duration-200 ease-in-out md:flex",
        collapsed ? "w-[60px]" : "w-64",
      )}
    >
      {collapsed ? (
        <SidebarRail />
      ) : (
        <SidebarContent onCollapse={toggleSidebarCollapsed} />
      )}
    </aside>
  );
}
