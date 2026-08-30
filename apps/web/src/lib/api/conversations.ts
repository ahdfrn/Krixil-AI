import { MOCK_CONVERSATIONS, MOCK_MESSAGES } from "@/lib/mock/conversations";
import type { ChatMessage, Conversation } from "@/types/chat";

/**
 * Phase 1: reads the static mock dataset. Phase 2: these become real calls to
 * GET/POST/PATCH/DELETE /api/v1/conversations — only this file changes; the Zustand store and
 * every component that calls it stay the same.
 */
export async function listConversations(): Promise<Conversation[]> {
  await new Promise((resolve) => setTimeout(resolve, 200));
  return MOCK_CONVERSATIONS;
}

export async function getConversationMessages(conversationId: string): Promise<ChatMessage[]> {
  await new Promise((resolve) => setTimeout(resolve, 150));
  return MOCK_MESSAGES[conversationId] ?? [];
}
