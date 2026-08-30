import { Sparkles } from "lucide-react";

import { SuggestionCards } from "@/components/chat/suggestion-cards";

export function ChatHome({ onSelectSuggestion }: { onSelectSuggestion: (prompt: string) => void }) {
  return (
    <div className="mx-auto flex w-full max-w-2xl flex-1 flex-col items-center justify-center px-4 text-center">
      <div className="mb-5 flex size-12 items-center justify-center rounded-2xl bg-primary text-primary-foreground">
        <Sparkles className="size-6" />
      </div>
      <h1 className="text-2xl font-semibold tracking-tight">Krixil AI</h1>
      <p className="mt-2 max-w-md text-sm text-muted-foreground">
        Your intelligent AI workspace. Ask questions, analyze data, create content, research
        ideas, write code, and get things done.
      </p>

      <div className="mt-8 w-full">
        <SuggestionCards onSelect={onSelectSuggestion} />
      </div>
    </div>
  );
}
