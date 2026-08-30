import { apiFetch } from "@/lib/api/client";
import type { ChatMessage, Conversation } from "@/types/chat";

interface ConversationOut {
  id: string;
  title: string;
  created_at: string;
}

interface MessageOut {
  id: string;
  role: string;
  content: string;
  created_at: string;
}

interface ConversationDetailOut extends ConversationOut {
  messages: MessageOut[];
}

// The backend doesn't track updated_at, model, pinned, or archived on a conversation — this
// mapping fills in the closest honest defaults rather than inventing data. See web-phase2.md.
function toConversation(c: ConversationOut): Conversation {
  return {
    id: c.id,
    title: c.title,
    createdAt: c.created_at,
    updatedAt: c.created_at,
    model: "auto",
  };
}

function toMessage(m: MessageOut, conversationId: string): ChatMessage {
  return {
    id: m.id,
    conversationId,
    role: m.role === "user" ? "user" : "assistant",
    content: m.content,
    createdAt: m.created_at,
    // Citations only arrive live in the SSE stream for that turn — history has none to show.
  };
}

export async function listConversations(): Promise<Conversation[]> {
  const raw = await apiFetch<ConversationOut[]>("/conversations");
  return raw.map(toConversation);
}

export async function getConversationMessages(conversationId: string): Promise<ChatMessage[]> {
  const detail = await apiFetch<ConversationDetailOut>(`/conversations/${conversationId}`);
  return detail.messages.map((m) => toMessage(m, conversationId));
}
