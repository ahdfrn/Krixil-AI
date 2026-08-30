import { BookOpen } from "lucide-react";

import { ComingSoon } from "@/components/layout/coming-soon";

export default function KnowledgePage() {
  return (
    <ComingSoon
      icon={BookOpen}
      title="Knowledge"
      description="Upload documents and search your tenant's knowledge base."
      phase="Phase 3"
    />
  );
}
