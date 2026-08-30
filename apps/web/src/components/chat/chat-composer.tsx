"use client";

import { ArrowUp, Mic, Paperclip, Square, Wrench } from "lucide-react";
import { nanoid } from "nanoid";
import { useEffect, useRef, useState } from "react";
import { toast } from "sonner";

import type { ComposerAttachment } from "@/components/chat/file-attachment-chip";
import { FileAttachmentChip, formatBytes } from "@/components/chat/file-attachment-chip";
import { ModelSelector } from "@/components/chat/model-selector";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";
import { ApiError } from "@/lib/api/client";
import { uploadDocument } from "@/lib/api/documents";
import { cn } from "@/lib/utils";
import { useChatStore } from "@/stores/chat-store";
import type { ModelId } from "@/types/chat";

const ACCEPTED_EXTENSIONS = [".pdf", ".docx", ".txt", ".csv"];

export function ChatComposer({
  onSend,
  isGenerating,
  onStop,
  initialValue,
}: {
  onSend: (content: string) => void;
  isGenerating: boolean;
  onStop: () => void;
  initialValue?: string;
}) {
  const [value, setValue] = useState(initialValue ?? "");
  const [attachments, setAttachments] = useState<ComposerAttachment[]>([]);
  const [isDragging, setIsDragging] = useState(false);
  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);
  const dragCounter = useRef(0);

  const selectedModel = useChatStore((s) => s.selectedModel);
  const setSelectedModel = useChatStore((s) => s.setSelectedModel);

  function autoResize() {
    const el = textareaRef.current;
    if (!el) return;
    el.style.height = "auto";
    el.style.height = `${Math.min(el.scrollHeight, 200)}px`;
  }

  useEffect(() => {
    if (initialValue) {
      autoResize();
      textareaRef.current?.focus();
    }
    // Intentionally mount-only: a new initialValue arrives via remount (see the `key` prop
    // ChatHomePage uses), not a prop update on an already-mounted composer.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  function addFiles(files: FileList | File[]) {
    const list = Array.from(files);
    for (const file of list) {
      const id = nanoid(8);
      const ext = file.name.slice(file.name.lastIndexOf(".")).toLowerCase();
      if (!ACCEPTED_EXTENSIONS.includes(ext)) {
        toast.error(`"${file.name}" isn't a supported file type — allowed: pdf, docx, txt, csv.`);
        continue;
      }

      setAttachments((prev) => [
        ...prev,
        { id, name: file.name, sizeLabel: formatBytes(file.size), status: "uploading" },
      ]);

      // Uploading adds the file to your knowledge base (tenant-wide RAG search), not to this
      // specific message — the backend has no per-message attachment concept.
      uploadDocument(file)
        .then((doc) => {
          if (doc.status === "ready") {
            setAttachments((prev) => prev.map((a) => (a.id === id ? { ...a, status: "ready" } : a)));
            toast.success(`"${file.name}" added to your knowledge base.`);
          } else {
            setAttachments((prev) => prev.map((a) => (a.id === id ? { ...a, status: "error" } : a)));
            toast.error(doc.error_message ?? `"${file.name}" couldn't be processed.`);
          }
        })
        .catch((err) => {
          setAttachments((prev) => prev.map((a) => (a.id === id ? { ...a, status: "error" } : a)));
          toast.error(err instanceof ApiError ? err.message : `"${file.name}" failed to upload.`);
        });
    }
  }

  function handleSend() {
    const trimmed = value.trim();
    if (!trimmed || isGenerating) return;
    onSend(trimmed);
    setValue("");
    requestAnimationFrame(autoResize);
  }

  return (
    <div
      className="relative border-t border-border bg-background px-3 pt-3 pb-3 md:px-4"
      onDragEnter={(e) => {
        e.preventDefault();
        dragCounter.current += 1;
        setIsDragging(true);
      }}
      onDragLeave={(e) => {
        e.preventDefault();
        dragCounter.current -= 1;
        if (dragCounter.current <= 0) setIsDragging(false);
      }}
      onDragOver={(e) => e.preventDefault()}
      onDrop={(e) => {
        e.preventDefault();
        dragCounter.current = 0;
        setIsDragging(false);
        if (e.dataTransfer.files.length) addFiles(e.dataTransfer.files);
      }}
    >
      {isDragging && (
        <div className="absolute inset-2 z-10 flex items-center justify-center rounded-xl border-2 border-dashed border-primary bg-background/90 text-sm font-medium text-primary">
          Drop files to attach
        </div>
      )}

      <div className="mx-auto w-full max-w-3xl">
        <div className="rounded-2xl border border-border bg-card shadow-sm">
          {attachments.length > 0 && (
            <div className="flex flex-wrap gap-2 border-b border-border px-3 pt-3 pb-2">
              {attachments.map((a) => (
                <FileAttachmentChip
                  key={a.id}
                  attachment={a}
                  onRemove={() =>
                    setAttachments((prev) => prev.filter((x) => x.id !== a.id))
                  }
                />
              ))}
            </div>
          )}

          <textarea
            ref={textareaRef}
            value={value}
            onChange={(e) => {
              setValue(e.target.value);
              autoResize();
            }}
            onKeyDown={(e) => {
              if (e.key === "Enter" && !e.shiftKey) {
                e.preventDefault();
                handleSend();
              }
            }}
            rows={1}
            placeholder="Ask Krixil anything..."
            aria-label="Message Krixil AI"
            className="max-h-[200px] w-full resize-none bg-transparent px-4 pt-3 pb-1 text-sm outline-none placeholder:text-muted-foreground"
          />

          <div className="flex items-center gap-1 px-2 pb-2">
            <input
              ref={fileInputRef}
              type="file"
              multiple
              className="hidden"
              accept={ACCEPTED_EXTENSIONS.join(",")}
              onChange={(e) => {
                if (e.target.files?.length) addFiles(e.target.files);
                e.target.value = "";
              }}
            />
            <ComposerIconButton
              label="Attach files"
              icon={Paperclip}
              onClick={() => fileInputRef.current?.click()}
            />
            <ComposerIconButton
              label="Tools"
              icon={Wrench}
              onClick={() => toast.info("Tool selection UI lands with Phase 3.")}
            />
            <ComposerIconButton
              label="Voice input"
              icon={Mic}
              onClick={() => toast.info("Voice input isn't wired up in this phase yet.")}
            />

            <div className="mx-1 h-5 w-px bg-border" />

            <ModelSelector value={selectedModel} onChange={setSelectedModel as (id: ModelId) => void} size="sm" />

            <div className="ml-auto">
              {isGenerating ? (
                <Tooltip>
                  <TooltipTrigger asChild>
                    <button
                      type="button"
                      onClick={onStop}
                      aria-label="Stop generating"
                      className="flex size-8 items-center justify-center rounded-full bg-foreground text-background hover:opacity-90"
                    >
                      <Square className="size-3.5 fill-current" />
                    </button>
                  </TooltipTrigger>
                  <TooltipContent>Stop generating</TooltipContent>
                </Tooltip>
              ) : (
                <button
                  type="button"
                  onClick={handleSend}
                  disabled={!value.trim()}
                  aria-label="Send message"
                  className={cn(
                    "flex size-8 items-center justify-center rounded-full transition-colors",
                    value.trim()
                      ? "bg-primary text-primary-foreground hover:bg-primary/90"
                      : "bg-secondary text-muted-foreground",
                  )}
                >
                  <ArrowUp className="size-4" />
                </button>
              )}
            </div>
          </div>
        </div>
        <p className="mt-1.5 text-center text-[11px] text-muted-foreground">
          Krixil can make mistakes. Consider checking important information.
        </p>
      </div>
    </div>
  );
}

function ComposerIconButton({
  label,
  icon: Icon,
  onClick,
}: {
  label: string;
  icon: React.ComponentType<{ className?: string }>;
  onClick: () => void;
}) {
  return (
    <Tooltip>
      <TooltipTrigger asChild>
        <button
          type="button"
          onClick={onClick}
          aria-label={label}
          className="flex size-8 items-center justify-center rounded-md text-muted-foreground hover:bg-secondary hover:text-foreground"
        >
          <Icon className="size-4" />
        </button>
      </TooltipTrigger>
      <TooltipContent>{label}</TooltipContent>
    </Tooltip>
  );
}
