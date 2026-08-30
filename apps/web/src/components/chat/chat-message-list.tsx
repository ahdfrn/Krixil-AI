"use client";

import { useEffect, useRef } from "react";

import { AssistantMessage } from "@/components/chat/assistant-message";
import { UserMessage } from "@/components/chat/user-message";
import { Skeleton } from "@/components/ui/skeleton";
import type { ChatMessage } from "@/types/chat";

export function ChatMessageList({
  messages,
  isLoading,
}: {
  messages: ChatMessage[];
  isLoading?: boolean;
}) {
  const bottomRef = useRef<HTMLDivElement>(null);
  const lastMessage = messages[messages.length - 1];

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth", block: "end" });
  }, [messages.length, lastMessage?.content]);

  if (isLoading) {
    return (
      <div className="mx-auto flex w-full max-w-3xl flex-col gap-4 px-4 py-6">
        <Skeleton className="ml-auto h-9 w-2/5 rounded-2xl" />
        <Skeleton className="h-24 w-4/5 rounded-lg" />
        <Skeleton className="ml-auto h-9 w-1/3 rounded-2xl" />
        <Skeleton className="h-16 w-3/5 rounded-lg" />
      </div>
    );
  }

  return (
    <div className="mx-auto w-full max-w-3xl py-4">
      {messages.map((message) =>
        message.role === "user" ? (
          <UserMessage key={message.id} message={message} />
        ) : (
          <AssistantMessage key={message.id} message={message} />
        ),
      )}
      <div ref={bottomRef} />
    </div>
  );
}
