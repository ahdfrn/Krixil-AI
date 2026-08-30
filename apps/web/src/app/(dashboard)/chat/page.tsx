"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";
import { toast } from "sonner";

import { ChatComposer } from "@/components/chat/chat-composer";
import { ChatHome } from "@/components/chat/chat-home";
import { ApiError } from "@/lib/api/client";
import { useChatStore } from "@/stores/chat-store";

export default function ChatHomePage() {
  const router = useRouter();
  const sendMessage = useChatStore((s) => s.sendMessage);
  const [pendingPrompt, setPendingPrompt] = useState("");
  const [isSending, setIsSending] = useState(false);

  async function handleSend(content: string) {
    setIsSending(true);
    try {
      // Resolves once the backend confirms the new conversation's real id (the first SSE event)
      // — the response keeps streaming into the store in the background after that, so the
      // conversation page picks it up mid-stream (or already finished) as soon as it mounts.
      const id = await sendMessage(null, content);
      router.push(`/chat/${id}`);
    } catch (err) {
      setIsSending(false);
      toast.error(err instanceof ApiError ? err.message : "Couldn't send that — check your connection.");
    }
  }

  return (
    <div className="flex flex-1 flex-col overflow-hidden">
      <ChatHome onSelectSuggestion={setPendingPrompt} />
      <ChatComposerWithPrefill prefill={pendingPrompt} onSend={handleSend} isGenerating={isSending} />
    </div>
  );
}

// Small wrapper so a suggestion-card click can prefill the composer without ChatComposer having
// to manage "controlled from outside" complexity for the common (typed by hand) case.
function ChatComposerWithPrefill({
  prefill,
  onSend,
  isGenerating,
}: {
  prefill: string;
  onSend: (content: string) => void;
  isGenerating: boolean;
}) {
  const stopGenerating = useChatStore((s) => s.stopGenerating);
  return (
    <ChatComposer
      key={prefill}
      onSend={onSend}
      isGenerating={isGenerating}
      onStop={stopGenerating}
      initialValue={prefill}
    />
  );
}
