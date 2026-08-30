import { Bot } from "lucide-react";

import { ComingSoon } from "@/components/layout/coming-soon";

export default function AgentsPage() {
  return (
    <ComingSoon
      icon={Bot}
      title="AI Agents"
      description="Run specialized agents — research, coding, data analysis, and more."
      phase="Phase 3"
    />
  );
}
