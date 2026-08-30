/**
 * Canned assistant replies used only to demonstrate the message UI (markdown, code blocks,
 * lists, tables) while streaming, per PHASE 1's "mock data" scope. Replaced in Phase 2 by the
 * real streaming response from POST /api/v1/chat/stream — see src/lib/api/messages.ts, which is
 * the only place that changes.
 */
const CANNED_RESPONSES = [
  "That's a great question. Let me break this down for you.\n\n" +
    "Here's what I'd suggest:\n\n" +
    "1. **Start with the fundamentals** — get the core logic working first.\n" +
    "2. **Iterate quickly** — small, testable changes beat big rewrites.\n" +
    "3. **Measure before optimizing** — don't guess where the bottleneck is.\n\n" +
    "Would you like me to go deeper on any of these?",
  "Here's a quick summary:\n\n" +
    "> The key insight is that small, consistent improvements compound over time far more " +
    "reliably than occasional large ones.\n\n" +
    "```python\ndef compound_growth(principal, rate, periods):\n    return principal * (1 + rate) ** periods\n```\n\n" +
    "Let me know if you'd like this adapted to a different scenario.",
  "Sure — here's a comparison:\n\n" +
    "| Option | Pros | Cons |\n" +
    "|---|---|---|\n" +
    "| A | Fast to ship | Less flexible |\n" +
    "| B | Highly flexible | Slower to ship |\n\n" +
    "For most cases I'd lean toward **Option A** first, and revisit **Option B** once you " +
    "have real usage data to justify the extra complexity.",
];

export function pickCannedResponse(seed: string): string {
  let hash = 0;
  for (let i = 0; i < seed.length; i++) {
    hash = (hash * 31 + seed.charCodeAt(i)) | 0;
  }
  const index = Math.abs(hash) % CANNED_RESPONSES.length;
  return CANNED_RESPONSES[index];
}

/** Yields the response word-by-word to simulate token streaming. */
export async function* streamCannedResponse(
  content: string,
  signal: AbortSignal,
): AsyncGenerator<string> {
  const words = content.split(" ");
  for (const word of words) {
    if (signal.aborted) return;
    await new Promise((resolve) => setTimeout(resolve, 18 + Math.random() * 35));
    yield word + " ";
  }
}
