import type { ChatMessage } from "@/types/chat";

export function UserMessage({ message }: { message: ChatMessage }) {
  return (
    <div className="flex justify-end px-4 py-2">
      <div className="max-w-[85%] rounded-2xl rounded-br-sm bg-primary px-4 py-2.5 text-sm text-primary-foreground whitespace-pre-wrap">
        {message.content}
      </div>
    </div>
  );
}
