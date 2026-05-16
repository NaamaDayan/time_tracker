import type { EventInput } from "@fullcalendar/core";
import type { ActivityWindow, Segment } from "./types";

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

export function segmentsToCalendarEvents(segments: Segment[]): EventInput[] {
  return segments.map((seg) => {
    const allDay = segmentIsAllDay(seg);
    const title = segmentTitle(seg);
    const range = allDay ? allDayRange(seg) : null;

    return {
      id: String(seg.id),
      title,
      start: range?.start ?? seg.started_at,
      end: range?.end ?? seg.ended_at,
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

export function windowTitle(win: ActivityWindow): string {
  const base = win.activity_label;
  if (win.segment_ids.length > 1) {
    return `${base} (${win.segment_ids.length})`;
  }
  return base;
}

export function windowsToCalendarEvents(windows: ActivityWindow[]): EventInput[] {
  return windows.map((win) => {
    const allDay = windowIsAllDay(win);
    const range = allDay ? allDayRangeFromWindow(win) : null;
    const hasGoogle = win.sources.includes("google_calendar");
    const isManualOnly = win.sources.length === 1 && win.sources[0] === "manual";

    return {
      id: String(win.id),
      title: windowTitle(win),
      start: range?.start ?? win.started_at,
      end: range?.end ?? win.ended_at,
      allDay,
      backgroundColor: win.color,
      borderColor: hasGoogle ? "#0ea5e9" : win.color,
      classNames: [
        hasGoogle ? "fc-event-google" : "",
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
