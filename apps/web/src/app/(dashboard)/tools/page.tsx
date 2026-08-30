import { Wrench } from "lucide-react";

import { ComingSoon } from "@/components/layout/coming-soon";

export default function ToolsPage() {
  return (
    <ComingSoon
      icon={Wrench}
      title="Available Tools"
      description="See what tools Krixil AI can use on your behalf, and manage their permissions."
      phase="Phase 3"
    />
  );
}
