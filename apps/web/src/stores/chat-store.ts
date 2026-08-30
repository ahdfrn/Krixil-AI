import { nanoid } from "nanoid";
import { toast } from "sonner";
import { create } from "zustand";

import { streamMessage } from "@/lib/api/chat";
import { ApiError } from "@/lib/api/client";
import {
  deleteConversation as deleteConversationApi,
  getConversationMessages,
  listConversations,
  renameConversation as renameConversationApi,
} from "@/lib/api/conversations";
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
  /**
   * Resolves as soon as the real conversation id is known — for a brand-new conversation
   * (conversationId: null) that's the `type: "conversation"` SSE event, not stream completion.
   * The rest of the response keeps streaming into the store in the background after this
   * resolves; the caller (e.g. the chat-home page) awaits this only to know where to navigate.
   */
  sendMessage: (conversationId: string | null, content: string) => Promise<string>;
  stopGenerating: () => void;
  renameConversation: (id: string, title: string) => Promise<void>;
  deleteConversation: (id: string) => Promise<void>;
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
    try {
      const conversations = await listConversations();
      set({ conversations, isLoadingConversations: false });
    } catch {
      set({ isLoadingConversations: false });
      toast.error("Couldn't load your conversations.");
    }
  },

  loadMessages: async (conversationId) => {
    if (get().messagesByConversation[conversationId]) return;
    set({ isLoadingMessages: true });
    try {
      const messages = await getConversationMessages(conversationId);
      set((state) => ({
        messagesByConversation: { ...state.messagesByConversation, [conversationId]: messages },
        isLoadingMessages: false,
      }));
    } catch {
      set({ isLoadingMessages: false });
      toast.error("Couldn't load this conversation.");
    }
  },

  sendMessage: (conversationId, content) => {
    const userMessageId = nanoid(10);
    const assistantId = nanoid(10);
    const startedAt = new Date().toISOString();

    return new Promise<string>((resolve, reject) => {
      let settled = false;

      // Runs once the real conversation id is known — creates the Conversation record (if this
      // is a new one) and both messages in a single update, keyed by the real id from here on.
      function ensureInitialized(id: string) {
        set((state) => {
          const existing = state.messagesByConversation[id] ?? [];
          const isNew = !state.conversations.some((c) => c.id === id);
          const userMessage: ChatMessage = {
            id: userMessageId,
            conversationId: id,
            role: "user",
            content,
            createdAt: startedAt,
          };
          const placeholder: ChatMessage = {
            id: assistantId,
            conversationId: id,
            role: "assistant",
            content: "",
            createdAt: new Date().toISOString(),
            isStreaming: true,
          };
          // The backend always titles a new conversation the literal "New conversation" and
          // never derives it from the first message (and there's no rename endpoint to fix it
          // after the fact) — deriving a nicer title here would look right for this session and
          // then confusingly revert on the next reload, so this matches server truth instead.
          const now = new Date().toISOString();
          const conversations = isNew
            ? [
                { id, title: "New conversation", createdAt: now, updatedAt: now, model: "auto" as ModelId },
                ...state.conversations,
              ]
            : state.conversations.map((c) => (c.id === id ? { ...c, updatedAt: now } : c));
          return {
            conversations,
            messagesByConversation: { ...state.messagesByConversation, [id]: [...existing, userMessage, placeholder] },
            generatingConversationId: id,
          };
        });
      }

      function updateAssistant(id: string, patch: Partial<ChatMessage>) {
        set((state) => ({
          messagesByConversation: {
            ...state.messagesByConversation,
            [id]: state.messagesByConversation[id].map((m) =>
              m.id === assistantId ? { ...m, ...patch } : m,
            ),
          },
        }));
      }

      (async () => {
        abortController = new AbortController();
        let realId = conversationId;
        if (realId) ensureInitialized(realId);

        try {
          for await (const event of streamMessage(
            { conversationId, message: content, model: get().selectedModel },
            abortController.signal,
          )) {
            switch (event.type) {
              case "conversation": {
                realId = event.conversation_id;
                ensureInitialized(realId);
                settled = true;
                resolve(realId);
                break;
              }
              case "citations": {
                if (realId) updateAssistant(realId, { citations: event.citations });
                break;
              }
              case "chunk": {
                if (realId) {
                  const current = get().messagesByConversation[realId]?.find((m) => m.id === assistantId);
                  updateAssistant(realId, { content: (current?.content ?? "") + event.delta });
                }
                break;
              }
              case "done": {
                if (realId) updateAssistant(realId, { isStreaming: false });
                set({ generatingConversationId: null });
                break;
              }
              case "error": {
                throw new Error(event.detail);
              }
            }
          }
        } catch (err) {
          if (realId) {
            updateAssistant(realId, {
              isStreaming: false,
              content: get().messagesByConversation[realId]?.find((m) => m.id === assistantId)?.content
                || "*Something went wrong generating a response.*",
            });
            set({ generatingConversationId: null });
          }
          if (!settled) {
            settled = true;
            reject(err);
          } else {
            toast.error("The response stopped early — something went wrong.");
          }
        }
      })();
    });
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

  renameConversation: async (id, title) => {
    const previous = get().conversations;
    set((state) => ({
      conversations: state.conversations.map((c) => (c.id === id ? { ...c, title } : c)),
    }));
    try {
      await renameConversationApi(id, title);
    } catch (err) {
      set({ conversations: previous });
      toast.error(err instanceof ApiError ? err.message : "Couldn't rename that conversation.");
    }
  },

  deleteConversation: async (id) => {
    const previousConversations = get().conversations;
    const previousMessages = get().messagesByConversation;
    set((state) => {
      const rest = { ...state.messagesByConversation };
      delete rest[id];
      return {
        conversations: state.conversations.filter((c) => c.id !== id),
        messagesByConversation: rest,
      };
    });
    try {
      await deleteConversationApi(id);
    } catch (err) {
      set({ conversations: previousConversations, messagesByConversation: previousMessages });
      toast.error(err instanceof ApiError ? err.message : "Couldn't delete that conversation.");
    }
  },

  setSelectedModel: (model) => set({ selectedModel: model }),
}));
