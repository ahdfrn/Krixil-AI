"use client";

import { BookOpen, FileText, Loader2, Search, Trash2, Upload } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { toast } from "sonner";

import { formatBytes } from "@/components/chat/file-attachment-chip";
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from "@/components/ui/alert-dialog";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Skeleton } from "@/components/ui/skeleton";
import { ApiError } from "@/lib/api/client";
import {
  ACCEPTED_DOCUMENT_EXTENSIONS,
  deleteDocument,
  listDocuments,
  uploadDocument,
  type DocumentOut,
} from "@/lib/api/documents";
import { searchKnowledge, type SearchResult } from "@/lib/api/knowledge";

const STATUS_LABEL: Record<DocumentOut["status"], string> = {
  ready: "Ready",
  failed: "Failed",
  processing: "Processing",
};

export default function KnowledgePage() {
  const [documents, setDocuments] = useState<DocumentOut[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [isUploading, setIsUploading] = useState(false);
  const fileInputRef = useRef<HTMLInputElement>(null);
  const [deleteTarget, setDeleteTarget] = useState<DocumentOut | null>(null);

  const [query, setQuery] = useState("");
  const [isSearching, setIsSearching] = useState(false);
  const [results, setResults] = useState<SearchResult[] | null>(null);

  async function loadDocuments() {
    setIsLoading(true);
    try {
      setDocuments(await listDocuments());
    } catch (err) {
      toast.error(err instanceof ApiError ? err.message : "Couldn't load your documents.");
    } finally {
      setIsLoading(false);
    }
  }

  useEffect(() => {
    // Fetch-on-mount, same pattern as the rest of this app's data loading (chat-store.ts).
    // eslint-disable-next-line react-hooks/set-state-in-effect
    void loadDocuments();
  }, []);

  async function handleUpload(file: File) {
    const ext = file.name.slice(file.name.lastIndexOf(".")).toLowerCase();
    if (!ACCEPTED_DOCUMENT_EXTENSIONS.includes(ext)) {
      toast.error(`"${file.name}" isn't a supported file type — allowed: pdf, docx, txt, csv.`);
      return;
    }
    setIsUploading(true);
    try {
      const doc = await uploadDocument(file);
      setDocuments((prev) => [doc, ...prev]);
      if (doc.status === "ready") {
        toast.success(`"${file.name}" added to your knowledge base.`);
      } else {
        toast.error(doc.error_message ?? `"${file.name}" couldn't be processed.`);
      }
    } catch (err) {
      toast.error(err instanceof ApiError ? err.message : `"${file.name}" failed to upload.`);
    } finally {
      setIsUploading(false);
    }
  }

  async function confirmDelete() {
    if (!deleteTarget) return;
    const target = deleteTarget;
    setDeleteTarget(null);
    try {
      await deleteDocument(target.id);
      setDocuments((prev) => prev.filter((d) => d.id !== target.id));
      toast.success(`"${target.filename}" deleted.`);
    } catch (err) {
      toast.error(err instanceof ApiError ? err.message : "Couldn't delete that document.");
    }
  }

  async function handleSearch(e: React.FormEvent) {
    e.preventDefault();
    const trimmed = query.trim();
    if (!trimmed) return;
    setIsSearching(true);
    try {
      setResults(await searchKnowledge(trimmed));
    } catch (err) {
      toast.error(err instanceof ApiError ? err.message : "Search failed.");
    } finally {
      setIsSearching(false);
    }
  }

  return (
    <div className="flex flex-1 flex-col overflow-hidden">
      <header className="flex h-12 shrink-0 items-center justify-between border-b border-border px-4">
        <h1 className="text-sm font-medium">Knowledge</h1>
        <div>
          <input
            ref={fileInputRef}
            type="file"
            className="hidden"
            accept={ACCEPTED_DOCUMENT_EXTENSIONS.join(",")}
            onChange={(e) => {
              const f = e.target.files?.[0];
              if (f) void handleUpload(f);
              e.target.value = "";
            }}
          />
          <Button size="sm" onClick={() => fileInputRef.current?.click()} disabled={isUploading}>
            {isUploading ? <Loader2 className="size-3.5 animate-spin" /> : <Upload className="size-3.5" />}
            Upload
          </Button>
        </div>
      </header>

      <div className="scrollbar-thin flex-1 overflow-y-auto px-4 py-6">
        <div className="mx-auto flex w-full max-w-3xl flex-col gap-6">
          <form onSubmit={handleSearch} className="flex gap-2">
            <Input
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              placeholder="Search your knowledge base..."
              className="flex-1"
            />
            <Button type="submit" variant="secondary" disabled={isSearching}>
              {isSearching ? <Loader2 className="size-3.5 animate-spin" /> : <Search className="size-3.5" />}
              Search
            </Button>
          </form>

          {results && (
            <div className="flex flex-col gap-2">
              <p className="text-xs text-muted-foreground">
                {results.length} result{results.length === 1 ? "" : "s"}
              </p>
              {results.length === 0 ? (
                <p className="rounded-lg border border-dashed border-border p-4 text-center text-sm text-muted-foreground">
                  No matches found.
                </p>
              ) : (
                results.map((r) => (
                  <div key={r.chunk_id} className="rounded-lg border border-border p-3 text-sm">
                    <div className="mb-1 flex items-center gap-2 text-xs text-muted-foreground">
                      <FileText className="size-3.5" />
                      <span className="font-medium text-foreground">{r.filename}</span>
                      {r.page != null && <span>· p.{r.page}</span>}
                      <span className="ml-auto">score {r.score.toFixed(2)}</span>
                    </div>
                    <p className="line-clamp-3 text-muted-foreground">{r.content}</p>
                  </div>
                ))
              )}
            </div>
          )}

          <div className="flex flex-col gap-2">
            <h2 className="text-xs font-medium text-muted-foreground">Documents</h2>
            {isLoading ? (
              <div className="flex flex-col gap-2">
                {Array.from({ length: 3 }).map((_, i) => (
                  <Skeleton key={i} className="h-16 w-full rounded-lg" />
                ))}
              </div>
            ) : documents.length === 0 ? (
              <div className="flex flex-col items-center gap-2 rounded-xl border border-dashed border-border p-8 text-center">
                <BookOpen className="size-6 text-muted-foreground" />
                <p className="text-sm text-muted-foreground">No documents yet. Upload one to get started.</p>
              </div>
            ) : (
              documents.map((doc) => (
                <div key={doc.id} className="flex items-center gap-3 rounded-lg border border-border p-3">
                  <FileText className="size-4 shrink-0 text-muted-foreground" />
                  <div className="min-w-0 flex-1">
                    <p className="truncate text-sm font-medium">{doc.filename}</p>
                    <p className="text-xs text-muted-foreground">
                      {formatBytes(doc.size_bytes)} · {doc.chunk_count} chunk{doc.chunk_count === 1 ? "" : "s"} ·{" "}
                      {new Date(doc.created_at).toLocaleDateString()}
                    </p>
                    {doc.status === "failed" && doc.error_message && (
                      <p className="mt-1 text-xs text-destructive">{doc.error_message}</p>
                    )}
                  </div>
                  <Badge variant={doc.status === "ready" ? "secondary" : doc.status === "failed" ? "destructive" : "outline"}>
                    {STATUS_LABEL[doc.status]}
                  </Badge>
                  <Button
                    variant="ghost"
                    size="icon-sm"
                    aria-label={`Delete ${doc.filename}`}
                    onClick={() => setDeleteTarget(doc)}
                  >
                    <Trash2 className="size-3.5" />
                  </Button>
                </div>
              ))
            )}
          </div>
        </div>
      </div>

      <AlertDialog open={!!deleteTarget} onOpenChange={(open) => !open && setDeleteTarget(null)}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>Delete this document?</AlertDialogTitle>
            <AlertDialogDescription>
              &ldquo;{deleteTarget?.filename}&rdquo; and everything indexed from it will be permanently deleted.
              This can&apos;t be undone.
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>Cancel</AlertDialogCancel>
            <AlertDialogAction className="bg-destructive text-white hover:bg-destructive/90" onClick={confirmDelete}>
              Delete
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </div>
  );
}
