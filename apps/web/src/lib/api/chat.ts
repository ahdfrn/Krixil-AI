import { API_BASE_URL } from "@/lib/api/client";
import { useAuthStore } from "@/stores/auth-store";
import type { Citation } from "@/types/chat";

interface BackendCitation {
  document_id: string;
  filename: string;
  page: number | null;
  chunk_index: number;
}

export type StreamEvent =
  | { type: "conversation"; conversation_id: string }
  | { type: "citations"; citations: Citation[] }
  | { type: "chunk"; delta: string }
  | { type: "done"; message_id: string; model: string }
  | { type: "error"; detail: string };

function mapCitations(raw: BackendCitation[]): Citation[] {
  return raw.map((c) => ({
    id: `${c.document_id}-${c.chunk_index}`,
    documentName: c.filename,
    page: c.page ?? undefined,
    // The backend doesn't return a snippet on chat citations — CitationList renders without one.
    snippet: "",
  }));
}

/**
 * Real SSE consumer for POST /chat/stream. Same async-generator + AbortSignal shape as Phase 1's
 * streamCannedResponse (chat-store.ts's consumption loop is written against that shape), but reads
 * genuine `data: {...}\n\n` frames off the network instead of yielding canned text.
 */
export async function* streamMessage(
  { conversationId, message, model }: { conversationId: string | null; message: string; model?: string },
  signal: AbortSignal,
): AsyncGenerator<StreamEvent> {
  const token = useAuthStore.getState().accessToken;

  const res = await fetch(`${API_BASE_URL}/chat/stream`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
    },
    body: JSON.stringify({ message, conversation_id: conversationId, model }),
    signal,
  });

  if (res.status === 401) {
    useAuthStore.getState().logout();
  }
  if (!res.ok || !res.body) {
    throw new Error(`Stream request failed (${res.status})`);
  }

  const reader = res.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";

  try {
    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, { stream: true });

      const frames = buffer.split("\n\n");
      buffer = frames.pop() ?? "";

      for (const frame of frames) {
        const line = frame.split("\n").find((l) => l.startsWith("data:"));
        if (!line) continue;
        const json = JSON.parse(line.slice(5).trim());

        if (json.type === "citations") {
          yield { type: "citations", citations: mapCitations(json.citations) };
        } else {
          yield json as StreamEvent;
        }
      }
    }
  } catch (err) {
    // An aborted fetch (Stop clicked) surfaces as an AbortError here — that's a clean stop, not
    // a real failure, so swallow it rather than let it reject the caller's `for await` loop.
    if (!(err instanceof DOMException && err.name === "AbortError")) throw err;
  } finally {
    reader.releaseLock();
  }
}
