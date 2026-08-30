export type MessageRole = "user" | "assistant";

export type ToolCallStatus = "running" | "done" | "error";

export interface ToolCallStep {
  id: string;
  label: string; // e.g. "Searching knowledge base" — user-facing, never a raw tool name
  status: ToolCallStatus;
}

export interface ToolCallSummary {
  id: string;
  steps: ToolCallStep[];
  summary: string; // e.g. "Analyzed 1,248 records" — shown collapsed
  details?: string; // shown when expanded ("View details")
}

export interface Citation {
  id: string;
  documentName: string;
  page?: number;
  snippet: string;
}

export interface ChatMessage {
  id: string;
  conversationId: string;
  role: MessageRole;
  content: string;
  createdAt: string;
  toolCalls?: ToolCallSummary[];
  citations?: Citation[];
  /** Only meaningful for the most recent assistant message while a response streams in. */
  isStreaming?: boolean;
}

export interface Conversation {
  id: string;
  title: string;
  createdAt: string;
  updatedAt: string;
  model: ModelId;
  pinned?: boolean;
  archived?: boolean;
}

export type ModelId = string;

export interface AIModel {
  id: ModelId;
  name: string;
  description: string;
  /** Lucide icon name, resolved by ModelSelector — keeps this type free of a React dependency. */
  icon: "sparkles" | "zap" | "brain" | "code" | "search";
}
