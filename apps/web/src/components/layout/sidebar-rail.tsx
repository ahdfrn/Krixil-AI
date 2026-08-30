"use client";

import { BookOpen, Bot, PanelLeftOpen, Plus, Search, Sparkles, Wrench } from "lucide-react";
import Link from "next/link";
import { useRouter } from "next/navigation";

import { UserMenu } from "@/components/layout/user-menu";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";
import { useUIStore } from "@/stores/ui-store";

const RAIL_ITEMS = [
  { href: "/knowledge", label: "Knowledge", icon: BookOpen },
  { href: "/agents", label: "Agents", icon: Bot },
  { href: "/tools", label: "Tools", icon: Wrench },
];

function RailButton({
  label,
  icon: Icon,
  onClick,
  href,
}: {
  label: string;
  icon: React.ComponentType<{ className?: string }>;
  onClick?: () => void;
  href?: string;
}) {
  const content = (
    <Tooltip>
      <TooltipTrigger asChild>
        {href ? (
          <Link
            href={href}
            className="flex size-9 items-center justify-center rounded-md text-sidebar-foreground/80 hover:bg-sidebar-accent hover:text-sidebar-accent-foreground"
          >
            <Icon className="size-4.5" />
          </Link>
        ) : (
          <button
            type="button"
            onClick={onClick}
            className="flex size-9 items-center justify-center rounded-md text-sidebar-foreground/80 hover:bg-sidebar-accent hover:text-sidebar-accent-foreground"
          >
            <Icon className="size-4.5" />
          </button>
        )}
      </TooltipTrigger>
      <TooltipContent side="right">{label}</TooltipContent>
    </Tooltip>
  );
  return content;
}

export function SidebarRail() {
  const router = useRouter();
  const toggleSidebarCollapsed = useUIStore((s) => s.toggleSidebarCollapsed);
  const setCommandMenuOpen = useUIStore((s) => s.setCommandMenuOpen);

  return (
    <div className="flex h-full flex-col items-center py-3">
      <Tooltip>
        <TooltipTrigger asChild>
          <button
            type="button"
            aria-label="Expand sidebar"
            onClick={toggleSidebarCollapsed}
            className="group flex size-8 items-center justify-center rounded-md bg-primary text-primary-foreground"
          >
            <Sparkles className="size-4 group-hover:hidden" />
            <PanelLeftOpen className="hidden size-4 group-hover:block" />
          </button>
        </TooltipTrigger>
        <TooltipContent side="right">Expand sidebar</TooltipContent>
      </Tooltip>

      <div className="mt-4 flex flex-col items-center gap-1">
        <RailButton label="New Chat" icon={Plus} onClick={() => router.push("/chat")} />
        <RailButton label="Search" icon={Search} onClick={() => setCommandMenuOpen(true)} />
      </div>

      <div className="mt-4 flex flex-col items-center gap-1 border-t border-sidebar-border pt-3">
        {RAIL_ITEMS.map((item) => (
          <RailButton key={item.href} label={item.label} icon={item.icon} href={item.href} />
        ))}
      </div>

      <div className="mt-auto">
        <UserMenu compact />
      </div>
    </div>
  );
}
