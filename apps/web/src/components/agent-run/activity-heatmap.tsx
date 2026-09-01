"use client";

// A GitHub-style activity grid — 7 day-rows × N week-columns, each cell shaded by how many runs
// happened that day. Weeks entirely before the tenant's very first run aren't shown, so a brand
// new account doesn't render months of empty gray squares.
const WEEKS = 12;
const DAY_MS = 24 * 60 * 60 * 1000;

function dateKey(d: Date): string {
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
}

function intensityClass(count: number): string {
  if (count === 0) return "bg-secondary";
  if (count === 1) return "bg-primary/30";
  if (count <= 3) return "bg-primary/55";
  if (count <= 6) return "bg-primary/75";
  return "bg-primary";
}

export function ActivityHeatmap({ activityByDate }: { activityByDate: Map<string, number> }) {
  const today = new Date();
  today.setHours(0, 0, 0, 0);
  // Align the grid's last column to end on the most recent Saturday so full weeks line up.
  const endOfWeek = new Date(today);
  endOfWeek.setDate(today.getDate() + (6 - today.getDay()));
  const totalDays = WEEKS * 7;
  const start = new Date(endOfWeek.getTime() - (totalDays - 1) * DAY_MS);

  const days: { key: string; count: number; inFuture: boolean }[] = [];
  for (let i = 0; i < totalDays; i++) {
    const d = new Date(start.getTime() + i * DAY_MS);
    const key = dateKey(d);
    days.push({ key, count: activityByDate.get(key) ?? 0, inFuture: d > today });
  }

  const columns: (typeof days)[] = [];
  for (let i = 0; i < WEEKS; i++) columns.push(days.slice(i * 7, i * 7 + 7));

  return (
    <div className="flex gap-[3px]" aria-hidden>
      {columns.map((week, i) => (
        <div key={i} className="flex flex-col gap-[3px]">
          {week.map((day) =>
            day.inFuture ? (
              <div key={day.key} className="size-2.5 rounded-sm" />
            ) : (
              <div
                key={day.key}
                title={`${day.key}: ${day.count} run${day.count === 1 ? "" : "s"}`}
                className={`size-2.5 rounded-sm ${intensityClass(day.count)}`}
              />
            ),
          )}
        </div>
      ))}
    </div>
  );
}
