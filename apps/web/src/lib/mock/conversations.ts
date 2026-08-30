import type { ChatMessage, Conversation } from "@/types/chat";

function hoursAgo(h: number): string {
  return new Date(Date.now() - h * 60 * 60 * 1000).toISOString();
}

function daysAgo(d: number): string {
  return new Date(Date.now() - d * 24 * 60 * 60 * 1000).toISOString();
}

export const MOCK_CONVERSATIONS: Conversation[] = [
  {
    id: "conv-1",
    title: "Improving Q3 sales strategy",
    createdAt: hoursAgo(2),
    updatedAt: hoursAgo(1),
    model: "auto",
    pinned: true,
  },
  {
    id: "conv-2",
    title: "Explain this Python decorator",
    createdAt: hoursAgo(5),
    updatedAt: hoursAgo(5),
    model: "coding",
  },
  {
    id: "conv-3",
    title: "Summarize the business plan PDF",
    createdAt: daysAgo(1),
    updatedAt: daysAgo(1),
    model: "research",
  },
  {
    id: "conv-4",
    title: "Brainstorm product names",
    createdAt: daysAgo(3),
    updatedAt: daysAgo(3),
    model: "fast",
  },
  {
    id: "conv-5",
    title: "Draft a customer follow-up email",
    createdAt: daysAgo(5),
    updatedAt: daysAgo(5),
    model: "fast",
  },
  {
    id: "conv-6",
    title: "Refactor the auth middleware",
    createdAt: daysAgo(21),
    updatedAt: daysAgo(21),
    model: "coding",
  },
];

export const MOCK_MESSAGES: Record<string, ChatMessage[]> = {
  "conv-1": [
    {
      id: "m1",
      conversationId: "conv-1",
      role: "user",
      content: "How can I improve my business this quarter? Use my sales data if you can.",
      createdAt: hoursAgo(2),
    },
    {
      id: "m2",
      conversationId: "conv-1",
      role: "assistant",
      content:
        "Here are a few strategies based on your recent sales data:\n\n" +
        "1. **Focus on your top 3 products** — they account for the majority of revenue this quarter.\n" +
        "2. **Re-engage lapsed customers** — a targeted follow-up campaign tends to have strong ROI.\n" +
        "3. **Bundle slow-moving inventory** with your best sellers to clear stock without discounting.\n\n" +
        "| Strategy | Effort | Expected impact |\n" +
        "|---|---|---|\n" +
        "| Focus on top products | Low | High |\n" +
        "| Re-engagement campaign | Medium | Medium |\n" +
        "| Bundle inventory | Low | Medium |\n\n" +
        "Want me to draft a follow-up email campaign for the lapsed customers?",
      createdAt: hoursAgo(1),
      toolCalls: [
        {
          id: "tc1",
          summary: "Analyzed 1,248 sales records",
          details:
            "Queried sales.get_summary and profit.get_analysis for the last 90 days, grouped by product category.",
          steps: [
            { id: "s1", label: "Searching knowledge base", status: "done" },
            { id: "s2", label: "Analyzing database", status: "done" },
            { id: "s3", label: "Running calculation", status: "done" },
            { id: "s4", label: "Checking results", status: "done" },
          ],
        },
      ],
      citations: [
        {
          id: "c1",
          documentName: "Q3-sales-report.xlsx",
          snippet: "Top 3 SKUs contributed 61% of gross revenue in the trailing 90 days.",
        },
      ],
    },
  ],
  "conv-2": [
    {
      id: "m3",
      conversationId: "conv-2",
      role: "user",
      content: "Can you explain what this decorator does?\n\n```python\ndef retry(times=3):\n    def wrapper(func):\n        def inner(*args, **kwargs):\n            for attempt in range(times):\n                try:\n                    return func(*args, **kwargs)\n                except Exception:\n                    if attempt == times - 1:\n                        raise\n        return inner\n    return wrapper\n```",
      createdAt: hoursAgo(5),
    },
    {
      id: "m4",
      conversationId: "conv-2",
      role: "assistant",
      content:
        "This is a **parameterized decorator** that retries a function call on failure.\n\n" +
        "- `retry(times=3)` is the outer function — it takes the configuration (how many attempts) and returns the actual decorator.\n" +
        "- `wrapper(func)` is the real decorator — it receives the function being decorated.\n" +
        "- `inner(*args, **kwargs)` is what actually runs in place of the original function. It calls `func`, and if it raises, retries up to `times` attempts before letting the exception propagate.\n\n" +
        "Usage would look like:\n\n```python\n@retry(times=5)\ndef flaky_network_call():\n    ...\n```\n\n" +
        "One thing to watch out for: this swallows every exception until the last attempt, which can hide the *type* of error that's actually happening. Adding a specific exception type (e.g. `except requests.ConnectionError:`) is usually safer than a bare `except Exception:`.",
      createdAt: hoursAgo(5),
    },
  ],
};
