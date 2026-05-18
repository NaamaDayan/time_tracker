import type { EventInput } from "@fullcalendar/core";
import type { ActivityWindow, Segment } from "./types";
import { utcIsoToCalendarLocal } from "./timezone";

export function segmentIsAllDay(seg: Segment): boolean {
  if (seg.metadata?.is_all_day === true) return true;
  if (seg.source !== "google_calendar") return false;
  const start = new Date(seg.started_at);
  const end = new Date(seg.ended_at);
  const durationMs = end.getTime() - start.getTime();
  return (
    durationMs >= 23 * 60 * 60 * 1000 &&
    start.getUTCHours() === 0 &&
    start.getUTCMinutes() === 0 &&
    end.getUTCHours() === 23 &&
    end.getUTCMinutes() >= 59
  );
}

function allDayRange(seg: Segment): { start: string; end: string } {
  const start = new Date(seg.started_at);
  const end = new Date(seg.ended_at);
  const startStr = start.toISOString().slice(0, 10);
  const endDay = new Date(
    Date.UTC(end.getUTCFullYear(), end.getUTCMonth(), end.getUTCDate() + 1)
  );
  return { start: startStr, end: endDay.toISOString().slice(0, 10) };
}

export function segmentIsEditable(seg: Segment): boolean {
  return seg.source === "manual";
}

export function segmentTitle(seg: Segment): string {
  const title =
    seg.metadata && typeof seg.metadata.title === "string"
      ? seg.metadata.title
      : null;
  const summary =
    seg.metadata && typeof seg.metadata.summary === "string"
      ? seg.metadata.summary
      : null;
  return title || summary || seg.activity_label;
}

export function segmentsToCalendarEvents(
  segments: Segment[],
  timeZone?: string
): EventInput[] {
  return segments.map((seg) => {
    const allDay = segmentIsAllDay(seg);
    const title = segmentTitle(seg);
    const range = allDay ? allDayRange(seg) : null;
    const start =
      range?.start ??
      (timeZone ? utcIsoToCalendarLocal(seg.started_at, timeZone) : seg.started_at);
    const end =
      range?.end ??
      (timeZone ? utcIsoToCalendarLocal(seg.ended_at, timeZone) : seg.ended_at);

    return {
      id: String(seg.id),
      title,
      start,
      end,
      allDay,
      backgroundColor: seg.color,
      borderColor: seg.source === "google_calendar" ? "#0ea5e9" : seg.color,
      classNames: [
        seg.source === "google_calendar" ? "fc-event-google" : "",
        seg.source === "manual" ? "fc-event-manual" : "",
      ].filter(Boolean),
      editable: segmentIsEditable(seg),
      extendedProps: {
        source: seg.source,
        activityType: seg.activity_type,
        segmentId: seg.id,
      },
    };
  });
}

function windowIsAllDay(win: ActivityWindow): boolean {
  const start = new Date(win.started_at);
  const end = new Date(win.ended_at);
  const durationMs = end.getTime() - start.getTime();
  return (
    durationMs >= 23 * 60 * 60 * 1000 &&
    start.getUTCHours() === 0 &&
    start.getUTCMinutes() === 0 &&
    end.getUTCHours() === 23 &&
    end.getUTCMinutes() >= 59
  );
}

function allDayRangeFromWindow(win: ActivityWindow): { start: string; end: string } {
  const start = new Date(win.started_at);
  const end = new Date(win.ended_at);
  const startStr = start.toISOString().slice(0, 10);
  const endDay = new Date(
    Date.UTC(end.getUTCFullYear(), end.getUTCMonth(), end.getUTCDate() + 1)
  );
  return { start: startStr, end: endDay.toISOString().slice(0, 10) };
}

/** Editable only when the window maps to a single manual segment. */
export function windowIsEditable(win: ActivityWindow): boolean {
  return (
    win.sources.length === 1 &&
    win.sources[0] === "manual" &&
    win.segment_ids.length === 1
  );
}

function healthTitleSuffix(metadata: Record<string, unknown> | null | undefined): string {
  if (!metadata) return "";
  const category = metadata.health_category;
  if (category === "exercise" && typeof metadata.exercise_type === "string") {
    return ` · ${metadata.exercise_type}`;
  }
  if (category === "sleep" && typeof metadata.woke_at === "string") {
    const woke = new Date(metadata.woke_at);
    if (!Number.isNaN(woke.getTime())) {
      return ` · woke ${woke.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" })}`;
    }
  }
  return "";
}

export function windowTitle(win: ActivityWindow): string {
  const meta = win.metadata as Record<string, unknown> | null | undefined;
  const healthSuffix =
    win.sources.includes("samsung_health") ? healthTitleSuffix(meta) : "";
  const base =
    meta?.health_category === "exercise"
      ? "Exercise"
      : meta?.health_category === "sleep"
        ? win.activity_label
        : win.activity_label;
  const title = `${base}${healthSuffix}`;
  if (win.segment_ids.length > 1) {
    return `${title} (${win.segment_ids.length})`;
  }
  return title;
}

export function windowsToCalendarEvents(
  windows: ActivityWindow[],
  timeZone?: string
): EventInput[] {
  return windows.map((win) => {
    const allDay = windowIsAllDay(win);
    const range = allDay ? allDayRangeFromWindow(win) : null;
    const hasGoogle = win.sources.includes("google_calendar");
    const hasHealth = win.sources.includes("samsung_health");
    const isManualOnly = win.sources.length === 1 && win.sources[0] === "manual";
    const start =
      range?.start ??
      (timeZone ? utcIsoToCalendarLocal(win.started_at, timeZone) : win.started_at);
    const end =
      range?.end ??
      (timeZone ? utcIsoToCalendarLocal(win.ended_at, timeZone) : win.ended_at);

    return {
      id: String(win.id),
      title: windowTitle(win),
      start,
      end,
      allDay,
      backgroundColor: win.color,
      borderColor: hasGoogle ? "#0ea5e9" : win.color,
      classNames: [
        hasGoogle ? "fc-event-google" : "",
        hasHealth ? "fc-event-health" : "",
        isManualOnly ? "fc-event-manual" : "",
        win.segment_ids.length > 1 ? "fc-event-merged" : "",
      ].filter(Boolean),
      editable: windowIsEditable(win),
      extendedProps: {
        sources: win.sources,
        activityType: win.activity_type,
        windowId: win.id,
        segmentIds: win.segment_ids,
      },
    };
  });
}
