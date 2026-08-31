import { apiFetch } from "@/lib/api/client";

export interface MemoryFact {
  id: string;
  content: string;
  created_at: string;
}

export async function listMemories(): Promise<MemoryFact[]> {
  return apiFetch<MemoryFact[]>("/memory");
}

export async function createMemory(content: string): Promise<MemoryFact> {
  return apiFetch<MemoryFact>("/memory", {
    method: "POST",
    body: JSON.stringify({ content }),
  });
}

export async function deleteMemory(id: string): Promise<void> {
  await apiFetch<void>(`/memory/${id}`, { method: "DELETE" });
}

export async function setMemoryEnabled(enabled: boolean): Promise<{ memory_enabled: boolean }> {
  return apiFetch<{ memory_enabled: boolean }>("/memory/settings", {
    method: "PATCH",
    body: JSON.stringify({ enabled }),
  });
}
