import { create } from "zustand";

import { listAgentRuns } from "@/lib/api/agents";
import { deriveCodeSessions, type CodeSession } from "@/lib/utils/code-sessions";

interface CodeSessionsState {
  sessions: CodeSession[];
  isLoading: boolean;
  loadSessions: () => Promise<void>;
}

// Small and separate from chat-store.ts on purpose — Code sessions are a different domain
// (derived, not a real persisted entity) and don't share any state with conversations. The
// sidebar loads this once on mount; code/page.tsx calls loadSessions() again after each run so a
// brand-new session shows up there immediately, not just after a refresh.
export const useCodeSessionsStore = create<CodeSessionsState>((set) => ({
  sessions: [],
  isLoading: true,

  loadSessions: async () => {
    set({ isLoading: true });
    try {
      const runs = await listAgentRuns();
      set({ sessions: deriveCodeSessions(runs), isLoading: false });
    } catch {
      set({ isLoading: false });
    }
  },
}));
