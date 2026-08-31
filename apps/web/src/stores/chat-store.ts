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
  /** Called on sign-out (manual or a silent 401) — clears any in-memory data from the previous
   * session so it can't briefly reappear (e.g. in the command menu) before a fresh fetch lands
   * for whoever logs in next in the same tab. See web-phase5.md. */
  resetChatState: () => void;
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
        // Tracks whether ensureInitialized has already run — needed because the backend always
        // sends a "conversation" SSE event first, even for an already-known conversation id, so
        // without this guard an existing conversation would get its user message + placeholder
        // appended twice (once here immediately, once again in the "conversation" case below).
        let initialized = false;
        if (realId) {
          ensureInitialized(realId);
          initialized = true;
        }

        // Accumulated locally rather than re-read from the store on every "chunk" event, so a
        // fast local model (many small SSE deltas per second) doesn't force a React re-render —
        // and downstream, a full markdown re-parse + re-render of the whole message tree — for
        // every single token. Flushed to the store at most once per animation frame instead; a
        // long or code-heavy response streamed at full speed was genuinely freezing the tab
        // (real bug, caught live) before this throttle existed.
        let streamedContent = "";
        let flushScheduled = false;
        function scheduleFlush() {
          if (flushScheduled) return;
          flushScheduled = true;
          requestAnimationFrame(() => {
            flushScheduled = false;
            if (realId) updateAssistant(realId, { content: streamedContent });
          });
        }

        try {
          for await (const event of streamMessage(
            { conversationId, message: content, model: get().selectedModel },
            abortController.signal,
          )) {
            switch (event.type) {
              case "conversation": {
                realId = event.conversation_id;
                if (!initialized) {
                  ensureInitialized(realId);
                  initialized = true;
                }
                settled = true;
                resolve(realId);
                break;
              }
              case "citations": {
                if (realId) updateAssistant(realId, { citations: event.citations });
                break;
              }
              case "tool_calls": {
                if (realId) updateAssistant(realId, { toolCalls: event.tool_calls });
                break;
              }
              case "chunk": {
                streamedContent += event.delta;
                scheduleFlush();
                break;
              }
              case "done": {
                // Flush synchronously here rather than waiting for the next animation frame —
                // otherwise a queued flush from just before "done" could land after this and
                // briefly show stale content with isStreaming already false.
                if (realId) updateAssistant(realId, { content: streamedContent, isStreaming: false });
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
              content: streamedContent || "*Something went wrong generating a response.*",
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

  resetChatState: () => {
    abortController?.abort();
    set({
      conversations: [],
      messagesByConversation: {},
      isLoadingConversations: true,
      isLoadingMessages: false,
      generatingConversationId: null,
    });
  },
}));
