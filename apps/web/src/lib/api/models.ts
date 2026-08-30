import { apiFetch } from "@/lib/api/client";
import type { AIModel } from "@/types/chat";

interface ModelOut {
  id: string;
  name: string;
  description: string;
}

// The backend has no concept of icons — that's a display-only concern. "auto" is the one real
// model that exists today; unrecognized future ids fall back to the same icon rather than erroring.
const ICON_BY_ID: Record<string, AIModel["icon"]> = {
  auto: "sparkles",
};

export async function listModels(): Promise<AIModel[]> {
  const raw = await apiFetch<ModelOut[]>("/models");
  return raw.map((m) => ({
    id: m.id,
    name: m.name,
    description: m.description,
    icon: ICON_BY_ID[m.id] ?? "sparkles",
  }));
}
