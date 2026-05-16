/** Week id uses ISO year/week number; calendar columns are Sun–Sat. */

export function getIsoWeek(date: Date = new Date()): string {
  const d = new Date(Date.UTC(date.getFullYear(), date.getMonth(), date.getDate()));
  const day = d.getUTCDay() || 7;
  d.setUTCDate(d.getUTCDate() + 4 - day);
  const yearStart = new Date(Date.UTC(d.getUTCFullYear(), 0, 1));
  const weekNo = Math.ceil(((d.getTime() - yearStart.getTime()) / 86400000 + 1) / 7);
  return `${d.getUTCFullYear()}-W${String(weekNo).padStart(2, "0")}`;
}

export function parseIsoWeek(week: string): { year: number; week: number } {
  const match = /^(\d{4})-W(\d{2})$/.exec(week);
  if (!match) throw new Error(`Invalid ISO week: ${week}`);
  return { year: Number(match[1]), week: Number(match[2]) };
}

function isoWeekMonday(year: number, week: number): Date {
  const jan4 = new Date(Date.UTC(year, 0, 4));
  const day = jan4.getUTCDay() || 7;
  const monday = new Date(jan4);
  monday.setUTCDate(jan4.getUTCDate() - day + 1 + (week - 1) * 7);
  return monday;
}

/** Sunday–Saturday range for the given ISO week id. */
export function weekDateRange(week: string): { from: Date; to: Date; days: Date[] } {
  const { year, week: w } = parseIsoWeek(week);
  const monday = isoWeekMonday(year, w);
  const sunday = new Date(monday);
  sunday.setUTCDate(monday.getUTCDate() - 1);

  const days = Array.from({ length: 7 }, (_, i) => {
    const d = new Date(sunday);
    d.setUTCDate(sunday.getUTCDate() + i);
    return d;
  });

  const from = days[0];
  const to = new Date(days[6]);
  to.setUTCHours(23, 59, 59, 999);
  return { from, to, days };
}

export function formatDayLabel(d: Date): string {
  return d.toLocaleDateString("en-US", { weekday: "short", month: "short", day: "numeric" });
}

export function shiftWeek(week: string, delta: number): string {
  const { days } = weekDateRange(week);
  const d = new Date(days[0]);
  d.setUTCDate(d.getUTCDate() + delta * 7);
  return getIsoWeek(d);
}
