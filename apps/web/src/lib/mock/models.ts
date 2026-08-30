import type { AIModel } from "@/types/chat";

/**
 * Phase 1 mock data. This is the ONLY file that will change when Phase 2 wires up the real
 * backend — see src/lib/api/models.ts, which every component calls instead of importing this
 * directly, so no UI component needs to change when the mock is swapped for a real fetch to
 * GET /api/v1/models.
 */
export const MOCK_MODELS: AIModel[] = [
  {
    id: "auto",
    name: "Krixil Auto",
    description: "Automatically picks the best model for your request",
    icon: "sparkles",
  },
  {
    id: "fast",
    name: "Fast",
    description: "Quick answers for everyday questions",
    icon: "zap",
  },
  {
    id: "reasoning",
    name: "Reasoning",
    description: "Deeper, step-by-step thinking for complex problems",
    icon: "brain",
  },
  {
    id: "coding",
    name: "Coding",
    description: "Specialized for writing and reviewing code",
    icon: "code",
  },
  {
    id: "research",
    name: "Research",
    description: "Searches and synthesizes information from multiple sources",
    icon: "search",
  },
];
