import { getIsoWeek, weekDateRange } from "./week";
import type { TimeWindowPreset } from "./types";

export function rangeForPreset(
  preset: TimeWindowPreset,
  customFrom?: string,
  customTo?: string,
  anchor: Date = new Date()
): { from: Date; to: Date; label: string } {
  if (preset === "custom" && customFrom && customTo) {
    const from = new Date(`${customFrom}T00:00:00`);
    const to = new Date(`${customTo}T23:59:59.999`);
    return { from, to, label: `${customFrom} – ${customTo}` };
  }

  const now = new Date(anchor);
  if (preset === "day") {
    const from = new Date(now);
    from.setHours(0, 0, 0, 0);
    const to = new Date(now);
    to.setHours(23, 59, 59, 999);
    return { from, to, label: from.toLocaleDateString() };
  }

  if (preset === "week") {
    const week = getIsoWeek(now);
    const { from, to } = weekDateRange(week);
    return { from, to, label: `Week ${week}` };
  }

  if (preset === "month") {
    const from = new Date(now.getFullYear(), now.getMonth(), 1);
    const to = new Date(now.getFullYear(), now.getMonth() + 1, 0, 23, 59, 59, 999);
    return {
      from,
      to,
      label: from.toLocaleDateString("en-US", { month: "long", year: "numeric" }),
    };
  }

  if (preset === "year") {
    const from = new Date(now.getFullYear(), 0, 1);
    const to = new Date(now.getFullYear(), 11, 31, 23, 59, 59, 999);
    return { from, to, label: String(now.getFullYear()) };
  }

  const week = getIsoWeek(now);
  const { from, to } = weekDateRange(week);
  return { from, to, label: `Week ${week}` };
}
