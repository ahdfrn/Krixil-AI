"use client";

import { Brain, Check, ChevronDown, Code2, Search, Sparkles, Zap } from "lucide-react";
import { useEffect, useState } from "react";

import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { listModels } from "@/lib/api/models";
import { cn } from "@/lib/utils";
import type { AIModel, ModelId } from "@/types/chat";

// Maps the *data-driven* icon key from AIModel.icon to an actual component — the model list
// itself still comes entirely from listModels() (mock now, a real API call in Phase 2), so
// adding a model server-side only requires it to use one of these existing icon keys, never a
// UI code change. See the master prompt's "Model Selector" section.
const ICONS: Record<AIModel["icon"], React.ComponentType<{ className?: string }>> = {
  sparkles: Sparkles,
  zap: Zap,
  brain: Brain,
  code: Code2,
  search: Search,
};

export function ModelSelector({
  value,
  onChange,
  size = "default",
}: {
  value: ModelId;
  onChange: (id: ModelId) => void;
  size?: "default" | "sm";
}) {
  const [models, setModels] = useState<AIModel[]>([]);

  useEffect(() => {
    listModels().then(setModels);
  }, []);

  const selected = models.find((m) => m.id === value);
  const SelectedIcon = selected ? ICONS[selected.icon] : Sparkles;

  return (
    <DropdownMenu>
      <DropdownMenuTrigger asChild>
        <button
          type="button"
          className={cn(
            "flex items-center gap-1.5 rounded-md text-muted-foreground hover:bg-accent hover:text-accent-foreground",
            size === "sm" ? "px-2 py-1 text-xs" : "px-2.5 py-1.5 text-sm",
          )}
        >
          <SelectedIcon className={size === "sm" ? "size-3.5" : "size-4"} />
          <span className="font-medium">{selected?.name ?? "Select model"}</span>
          <ChevronDown className="size-3.5 opacity-60" />
        </button>
      </DropdownMenuTrigger>
      <DropdownMenuContent align="start" className="w-72">
        {models.map((model) => {
          const Icon = ICONS[model.icon];
          return (
            <DropdownMenuItem
              key={model.id}
              onSelect={() => onChange(model.id)}
              className="items-start gap-2.5 py-2"
            >
              <Icon className="mt-0.5 size-4 shrink-0" />
              <div className="flex min-w-0 flex-col">
                <span className="text-sm">{model.name}</span>
                <span className="text-xs text-muted-foreground">{model.description}</span>
              </div>
              {model.id === value && <Check className="ml-auto size-4 shrink-0 self-center" />}
            </DropdownMenuItem>
          );
        })}
      </DropdownMenuContent>
    </DropdownMenu>
  );
}
