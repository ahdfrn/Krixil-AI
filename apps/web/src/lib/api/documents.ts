import { apiFetch } from "@/lib/api/client";

export interface DocumentOut {
  id: string;
  filename: string;
  content_type: string;
  size_bytes: number;
  status: "processing" | "ready" | "failed";
  chunk_count: number;
  error_message: string | null;
  created_at: string;
}

/**
 * Uploading adds the file to the tenant's knowledge base (tenant-wide RAG-searchable content) —
 * the backend has no per-message attachment concept, so this is not scoped to "this chat message."
 * Ingestion runs synchronously; by the time this resolves, `status` is already final
 * ("ready" or "failed"), never "processing" — there's no polling endpoint to check later.
 */
export async function uploadDocument(file: File, signal?: AbortSignal): Promise<DocumentOut> {
  const formData = new FormData();
  formData.append("file", file);

  return apiFetch<DocumentOut>("/documents", {
    method: "POST",
    body: formData,
    signal,
  });
}
