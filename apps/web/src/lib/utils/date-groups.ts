import type { Conversation } from "@/types/chat";

export type DateGroupLabel = "Today" | "Yesterday" | "Previous 7 Days" | "Older";

const GROUP_ORDER: DateGroupLabel[] = ["Today", "Yesterday", "Previous 7 Days", "Older"];

function groupLabelFor(isoDate: string): DateGroupLabel {
  const date = new Date(isoDate);
  const now = new Date();
  const startOfToday = new Date(now.getFullYear(), now.getMonth(), now.getDate());
  const startOfYesterday = new Date(startOfToday);
  startOfYesterday.setDate(startOfYesterday.getDate() - 1);
  const sevenDaysAgo = new Date(startOfToday);
  sevenDaysAgo.setDate(sevenDaysAgo.getDate() - 7);

  if (date >= startOfToday) return "Today";
  if (date >= startOfYesterday) return "Yesterday";
  if (date >= sevenDaysAgo) return "Previous 7 Days";
  return "Older";
}

/** Today/Yesterday/Previous 7 Days/Older bucketing, generic over anything with an `updatedAt` —
 * shared by Chat's conversation list and the Code sidebar's session list so both stay visually
 * consistent without duplicating the bucketing logic. */
export function groupByDate<T extends { updatedAt: string }>(
  items: T[],
): { label: DateGroupLabel; items: T[] }[] {
  const groups = new Map<DateGroupLabel, T[]>();
  for (const item of items) {
    const label = groupLabelFor(item.updatedAt);
    const existing = groups.get(label) ?? [];
    existing.push(item);
    groups.set(label, existing);
  }

  return GROUP_ORDER.filter((label) => groups.has(label)).map((label) => ({
    label,
    items: groups
      .get(label)!
      .sort((a, b) => new Date(b.updatedAt).getTime() - new Date(a.updatedAt).getTime()),
  }));
}

export function groupConversationsByDate(
  conversations: Conversation[],
): { label: DateGroupLabel; conversations: Conversation[] }[] {
  return groupByDate(conversations).map(({ label, items }) => ({ label, conversations: items }));
}
