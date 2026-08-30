import type { LucideIcon } from "lucide-react";

export function ComingSoon({
  icon: Icon,
  title,
  description,
  phase,
}: {
  icon: LucideIcon;
  title: string;
  description: string;
  phase: string;
}) {
  return (
    <div className="flex flex-1 flex-col overflow-hidden">
      <header className="flex h-12 shrink-0 items-center border-b border-border px-4">
        <h1 className="text-sm font-medium">{title}</h1>
      </header>
      <div className="flex flex-1 flex-col items-center justify-center gap-3 px-4 text-center">
        <div className="flex size-12 items-center justify-center rounded-2xl bg-secondary">
          <Icon className="size-6 text-muted-foreground" />
        </div>
        <div className="max-w-sm">
          <p className="text-sm font-medium">{description}</p>
          <p className="mt-1 text-xs text-muted-foreground">
            This page is UI-only for now, wired to real data in {phase}.
          </p>
        </div>
      </div>
    </div>
  );
}
