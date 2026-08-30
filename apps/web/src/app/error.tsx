"use client";

import { AlertTriangle, RotateCcw } from "lucide-react";
import Link from "next/link";
import { useEffect } from "react";

import { Button } from "@/components/ui/button";

export default function Error({
  error,
  reset,
}: {
  error: Error & { digest?: string };
  reset: () => void;
}) {
  useEffect(() => {
    console.error(error);
  }, [error]);

  return (
    <div className="flex min-h-dvh flex-col items-center justify-center gap-3 bg-background px-4 text-center">
      <div className="flex size-12 items-center justify-center rounded-2xl bg-secondary">
        <AlertTriangle className="size-6 text-muted-foreground" />
      </div>
      <div className="max-w-sm">
        <p className="text-sm font-medium">Something went wrong.</p>
        <p className="mt-1 text-xs text-muted-foreground">
          Krixil ran into an unexpected error. You can try again, or head back to your chats.
        </p>
      </div>
      <div className="mt-2 flex items-center gap-2">
        <Button size="sm" onClick={reset}>
          <RotateCcw className="size-3.5" />
          Try again
        </Button>
        <Button size="sm" variant="secondary" asChild>
          <Link href="/chat">Back to chat</Link>
        </Button>
      </div>
    </div>
  );
}
