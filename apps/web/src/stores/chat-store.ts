import { nanoid } from "nanoid";
import { create } from "zustand";

import { getConversationMessages, listConversations } from "@/lib/api/conversations";
import { pickCannedResponse, streamCannedResponse } from "@/lib/mock/responses";
import type { ChatMessage, Conversation, ModelId } from "@/types/chat";

interface ChatState {
  conversations: Conversation[];
  messagesByConversation: Record<string, ChatMessage[]>;
  isLoadingConversations: boolean;
  isLoadingMessages: boolean;
  generatingConversationId: string | null;
  selectedModel: ModelId;

  loadConversations: () => Promise<void>;
  loadMessages: (conversationId: string) => Promise<void>;
  createConversation: () => string;
  sendMessage: (conversationId: string | null, content: string) => Promise<string>;
  stopGenerating: () => void;
  renameConversation: (id: string, title: string) => void;
  deleteConversation: (id: string) => void;
  togglePin: (id: string) => void;
  toggleArchive: (id: string) => void;
  setSelectedModel: (model: ModelId) => void;
}

let abortController: AbortController | null = null;

export const useChatStore = create<ChatState>((set, get) => ({
  conversations: [],
  messagesByConversation: {},
  isLoadingConversations: true,
  isLoadingMessages: false,
  generatingConversationId: null,
  selectedModel: "auto",

  loadConversations: async () => {
    set({ isLoadingConversations: true });
    const conversations = await listConversations();
    set({ conversations, isLoadingConversations: false });
  },

  loadMessages: async (conversationId) => {
    if (get().messagesByConversation[conversationId]) return;
    set({ isLoadingMessages: true });
    const messages = await getConversationMessages(conversationId);
    set((state) => ({
      messagesByConversation: { ...state.messagesByConversation, [conversationId]: messages },
      isLoadingMessages: false,
    }));
  },

  createConversation: () => {
    const id = nanoid(10);
    const now = new Date().toISOString();
    const conversation: Conversation = {
      id,
      title: "New chat",
      createdAt: now,
      updatedAt: now,
      model: get().selectedModel,
    };
    set((state) => ({
      conversations: [conversation, ...state.conversations],
      messagesByConversation: { ...state.messagesByConversation, [id]: [] },
    }));
    return id;
  },

  sendMessage: async (conversationId, content) => {
    let id = conversationId;
    if (!id) {
      id = get().createConversation();
    }

    const userMessage: ChatMessage = {
      id: nanoid(10),
      conversationId: id,
      role: "user",
      content,
      createdAt: new Date().toISOString(),
    };

    const isFirstMessage = (get().messagesByConversation[id] ?? []).length === 0;

    set((state) => ({
      messagesByConversation: {
        ...state.messagesByConversation,
        [id!]: [...(state.messagesByConversation[id!] ?? []), userMessage],
      },
      conversations: state.conversations.map((c) =>
        c.id === id
          ? {
              ...c,
              updatedAt: new Date().toISOString(),
              title: isFirstMessage ? content.slice(0, 60) : c.title,
            }
          : c,
      ),
      generatingConversationId: id,
    }));

    const assistantId = nanoid(10);
    const placeholder: ChatMessage = {
      id: assistantId,
      conversationId: id,
      role: "assistant",
      content: "",
      createdAt: new Date().toISOString(),
      isStreaming: true,
      toolCalls: [
        {
          id: nanoid(6),
          summary: "Searching knowledge base",
          steps: [{ id: nanoid(6), label: "Searching knowledge base", status: "running" }],
        },
      ],
    };
    set((state) => ({
      messagesByConversation: {
        ...state.messagesByConversation,
        [id!]: [...state.messagesByConversation[id!], placeholder],
      },
    }));

    abortController = new AbortController();
    const responseText = pickCannedResponse(content);
    let accumulated = "";

    for await (const chunk of streamCannedResponse(responseText, abortController.signal)) {
      accumulated += chunk;
      set((state) => ({
        messagesByConversation: {
          ...state.messagesByConversation,
          [id!]: state.messagesByConversation[id!].map((m) =>
            m.id === assistantId ? { ...m, content: accumulated } : m,
          ),
        },
      }));
    }

    set((state) => ({
      messagesByConversation: {
        ...state.messagesByConversation,
        [id!]: state.messagesByConversation[id!].map((m) =>
          m.id === assistantId
            ? {
                ...m,
                content: accumulated.trim(),
                isStreaming: false,
                toolCalls: m.toolCalls?.map((tc) => ({
                  ...tc,
                  summary: "Searched 12 knowledge base entries",
                  details: "Ran a hybrid vector + keyword search over your uploaded documents.",
                  steps: tc.steps.map((s) => ({ ...s, status: "done" as const })),
                })),
              }
            : m,
        ),
      },
      generatingConversationId: null,
    }));

    return id!;
  },

  stopGenerating: () => {
    abortController?.abort();
    const id = get().generatingConversationId;
    if (!id) return;
    set((state) => ({
      messagesByConversation: {
        ...state.messagesByConversation,
        [id]: state.messagesByConversation[id].map((m) =>
          m.isStreaming ? { ...m, isStreaming: false, content: m.content || "*Stopped.*" } : m,
        ),
      },
      generatingConversationId: null,
    }));
  },

  renameConversation: (id, title) => {
    set((state) => ({
      conversations: state.conversations.map((c) => (c.id === id ? { ...c, title } : c)),
    }));
  },

  deleteConversation: (id) => {
    set((state) => {
      const rest = { ...state.messagesByConversation };
      delete rest[id];
      return {
        conversations: state.conversations.filter((c) => c.id !== id),
        messagesByConversation: rest,
      };
    });
  },

  togglePin: (id) => {
    set((state) => ({
      conversations: state.conversations.map((c) =>
        c.id === id ? { ...c, pinned: !c.pinned } : c,
      ),
    }));
  },

  toggleArchive: (id) => {
    set((state) => ({
      conversations: state.conversations.map((c) =>
        c.id === id ? { ...c, archived: !c.archived } : c,
      ),
    }));
  },

  setSelectedModel: (model) => set({ selectedModel: model }),
}));
