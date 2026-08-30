"use client";

import { useParams, useRouter } from "next/navigation";
import { useEffect } from "react";

import { ChatComposer } from "@/components/chat/chat-composer";
import { ChatHeader } from "@/components/chat/chat-header";
import { ChatMessageList } from "@/components/chat/chat-message-list";
import { useChatStore } from "@/stores/chat-store";

export default function ConversationPage() {
  const { conversationId } = useParams<{ conversationId: string }>();
  const router = useRouter();

  const conversation = useChatStore((s) =>
    s.conversations.find((c) => c.id === conversationId),
  );
  const messages = useChatStore((s) => s.messagesByConversation[conversationId]);
  const isLoadingMessages = useChatStore((s) => s.isLoadingMessages);
  const isLoadingConversations = useChatStore((s) => s.isLoadingConversations);
  const generatingConversationId = useChatStore((s) => s.generatingConversationId);
  const loadMessages = useChatStore((s) => s.loadMessages);
  const sendMessage = useChatStore((s) => s.sendMessage);
  const stopGenerating = useChatStore((s) => s.stopGenerating);

  useEffect(() => {
    loadMessages(conversationId);
  }, [conversationId, loadMessages]);

  useEffect(() => {
    // A brand-new conversation was created client-side but the id doesn't match anything after
    // conversations finished loading (e.g. a stale link) — send the user back to a safe state.
    if (!isLoadingConversations && !conversation) {
      router.replace("/chat");
    }
  }, [isLoadingConversations, conversation, router]);

  if (!conversation) return null;

  const isGenerating = generatingConversationId === conversationId;

  return (
    <div className="flex flex-1 flex-col overflow-hidden">
      <ChatHeader conversation={conversation} />
      <div className="scrollbar-thin flex-1 overflow-y-auto">
        <ChatMessageList messages={messages ?? []} isLoading={isLoadingMessages && !messages} />
      </div>
      <ChatComposer
        onSend={(content) => void sendMessage(conversationId, content)}
        isGenerating={isGenerating}
        onStop={stopGenerating}
      />
    </div>
  );
}
