"use client";

import { File as FileIcon, Loader2, X } from "lucide-react";

export interface ComposerAttachment {
  id: string;
  name: string;
  sizeLabel: string;
  status: "uploading" | "ready" | "error";
}

function formatBytes(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

export { formatBytes };

export function FileAttachmentChip({
  attachment,
  onRemove,
}: {
  attachment: ComposerAttachment;
  onRemove: () => void;
}) {
  return (
    <div className="flex items-center gap-2 rounded-lg border border-border bg-secondary/40 py-1.5 pr-1.5 pl-2.5 text-xs">
      <FileIcon className="size-4 shrink-0 text-muted-foreground" />
      <div className="flex min-w-0 flex-col">
        <span className="truncate font-medium">{attachment.name}</span>
        <span className="text-muted-foreground">
          {attachment.sizeLabel}
          {attachment.status === "uploading" && " · Uploading..."}
          {attachment.status === "ready" && " · Ready"}
          {attachment.status === "error" && " · Upload failed"}
        </span>
      </div>
      {attachment.status === "uploading" ? (
        <Loader2 className="size-3.5 shrink-0 animate-spin text-muted-foreground" />
      ) : (
        <button
          type="button"
          onClick={onRemove}
          aria-label={`Remove ${attachment.name}`}
          className="flex size-5 shrink-0 items-center justify-center rounded hover:bg-secondary"
        >
          <X className="size-3.5" />
        </button>
      )}
    </div>
  );
}
