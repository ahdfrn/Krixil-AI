import { MOCK_MODELS } from "@/lib/mock/models";
import type { AIModel } from "@/types/chat";

/**
 * Phase 1: returns static mock data. Phase 2: becomes `fetch("/api/v1/models")`. Nothing that
 * calls listModels() needs to change — this is the seam described in the master prompt's
 * "API Abstraction" section.
 */
export async function listModels(): Promise<AIModel[]> {
  await new Promise((resolve) => setTimeout(resolve, 120));
  return MOCK_MODELS;
}
