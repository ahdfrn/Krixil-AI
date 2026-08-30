import { FileText } from "lucide-react";

import { ComingSoon } from "@/components/layout/coming-soon";

export default function FilesPage() {
  return (
    <ComingSoon
      icon={FileText}
      title="Files"
      description="Everything you've uploaded across every conversation, in one place."
      phase="Phase 3"
    />
  );
}
