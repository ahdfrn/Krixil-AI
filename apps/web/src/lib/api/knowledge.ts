import { apiFetch } from "@/lib/api/client";

export interface SearchResult {
  chunk_id: string;
  document_id: string;
  filename: string;
  page: number | null;
  chunk_index: number;
  content: string;
  score: number;
}

export async function searchKnowledge(
  query: string,
  opts?: { topK?: number; documentId?: string },
): Promise<SearchResult[]> {
  return apiFetch<SearchResult[]>("/knowledge/search", {
    method: "POST",
    body: JSON.stringify({
      query,
      top_k: opts?.topK,
      document_id: opts?.documentId,
    }),
  });
}
