"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";

import { ChatComposer } from "@/components/chat/chat-composer";
import { ChatHome } from "@/components/chat/chat-home";
import { useChatStore } from "@/stores/chat-store";

export default function ChatHomePage() {
  const router = useRouter();
  const createConversation = useChatStore((s) => s.createConversation);
  const sendMessage = useChatStore((s) => s.sendMessage);
  const [pendingPrompt, setPendingPrompt] = useState("");

  function handleSend(content: string) {
    const id = createConversation();
    router.push(`/chat/${id}`);
    // Fire and forget — the conversation page reads from the same store, so it picks up the
    // user message and the streaming assistant reply as soon as it mounts.
    void sendMessage(id, content);
  }

  return (
    <div className="flex flex-1 flex-col overflow-hidden">
      <ChatHome onSelectSuggestion={setPendingPrompt} />
      <ChatComposerWithPrefill prefill={pendingPrompt} onSend={handleSend} />
    </div>
  );
}

// Small wrapper so a suggestion-card click can prefill the composer without ChatComposer having
// to manage "controlled from outside" complexity for the common (typed by hand) case.
function ChatComposerWithPrefill({
  prefill,
  onSend,
}: {
  prefill: string;
  onSend: (content: string) => void;
}) {
  return (
    <ChatComposer
      key={prefill}
      onSend={onSend}
      isGenerating={false}
      onStop={() => {}}
      initialValue={prefill}
    />
  );
}
