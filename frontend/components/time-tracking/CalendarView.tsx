"use client";

import type { EventContentArg } from "@fullcalendar/core";
import { useCallback, useEffect, useMemo, useState } from "react";
import { ActivityBlock } from "@/components/timeline/ActivityBlock";
import { CorrectionPopover } from "@/components/timeline/CorrectionPopover";
import {
  EventModal,
  eventFormFromRange,
  eventFormToIsoRange,
  type EventFormValues,
} from "@/components/EventModal";
import { WeekCalendar, type CalendarEventChange } from "@/components/WeekCalendar";
import { useWindowCorrections } from "@/hooks/useWindowCorrections";
import {
  createSegment,
  getWindows,
  updateSegment,
} from "@/lib/api";
import { windowIsEditable, windowTitle, windowsToCalendarEvents } from "@/lib/calendarEvents";
import type { ActivityType, ActivityWindow } from "@/lib/types";
import styles from "./CalendarView.module.css";

interface CalendarViewProps {
  timezone: string;
  activityTypes: ActivityType[];
  refreshKey: number;
  onDataChange?: () => void;
}

type ModalState = { kind: "closed" } | { kind: "create"; initial: EventFormValues };

const LOW_CONFIDENCE = 0.5;
const REVIEW_BANNER_MIN = 3;
const REVIEW_MAX_DAYS = 7;

function windowOnToday(win: ActivityWindow, timezone: string): boolean {
  const fmt = new Intl.DateTimeFormat("en-CA", {
    timeZone: timezone,
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
  });
  const today = fmt.format(new Date());
  const startDay = fmt.format(new Date(win.started_at));
  return startDay === today;
}

function daysSinceWindow(win: ActivityWindow, timezone: string): number {
  const end = new Date(win.ended_at);
  const now = new Date();
  const fmtDay = (d: Date) =>
    new Intl.DateTimeFormat("en-CA", { timeZone: timezone }).format(d);
  const endDay = fmtDay(end);
  const today = fmtDay(now);
  if (endDay === today) return 0;
  const diff = now.getTime() - end.getTime();
  return Math.floor(diff / (24 * 60 * 60 * 1000));
}

export function CalendarView({
  timezone,
  activityTypes,
  refreshKey,
  onDataChange,
}: CalendarViewProps) {
  const [range, setRange] = useState<{ from: Date; to: Date } | null>(null);
  const [windows, setWindows] = useState<ActivityWindow[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [toast, setToast] = useState<string | null>(null);
  const [modal, setModal] = useState<ModalState>({ kind: "closed" });
  const [modalError, setModalError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);
  const [popoverOpen, setPopoverOpen] = useState(false);
  const [selectedWindow, setSelectedWindow] = useState<ActivityWindow | null>(null);
  const [anchorPosition, setAnchorPosition] = useState<{ x: number; y: number } | null>(
    null
  );
  const [highlightEventId, setHighlightEventId] = useState<string | null>(null);

  const load = useCallback(async (from: Date, to: Date) => {
    setLoading(true);
    setError(null);
    try {
      const data = await getWindows(from.toISOString(), to.toISOString());
      setWindows(data.windows);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to load activities");
    } finally {
      setLoading(false);
    }
  }, []);

  const handleDatesChange = useCallback((from: Date, to: Date) => {
    setRange({ from, to });
  }, []);

  useEffect(() => {
    if (range) {
      load(range.from, range.to);
    }
  }, [range, load, refreshKey]);

  const corrections = useWindowCorrections({
    windows,
    setWindows,
    refetchRange: load,
    range,
    onError: (msg) => setToast(msg),
  });

  const events = useMemo(
    () => windowsToCalendarEvents(windows, timezone),
    [windows, timezone]
  );

  const windowById = useMemo(() => {
    const map = new Map<string, ActivityWindow>();
    for (const win of windows) map.set(String(win.id), win);
    return map;
  }, [windows]);

  const lowConfidenceToday = useMemo(() => {
    return windows.filter(
      (w) =>
        windowOnToday(w, timezone) &&
        daysSinceWindow(w, timezone) <= REVIEW_MAX_DAYS &&
        w.confidence < LOW_CONFIDENCE &&
        !w.confirmed_by_user &&
        !w.dismissed_by_user
    );
  }, [windows, timezone]);

  const showReviewBanner = lowConfidenceToday.length >= REVIEW_BANNER_MIN;

  const renderEventContent = useCallback(
    (arg: EventContentArg) => {
      const win = windowById.get(arg.event.id);
      if (!win) return undefined;
      return <ActivityBlock window={win} title={windowTitle(win)} />;
    },
    [windowById]
  );

  const openPopoverForWindow = useCallback(
    (win: ActivityWindow, rect: DOMRect) => {
      setSelectedWindow(win);
      setAnchorPosition({ x: rect.right, y: rect.top + rect.height / 2 });
      setPopoverOpen(true);
      setHighlightEventId(String(win.id));
    },
    []
  );

  const handleSelectRange = useCallback(
    (start: Date, end: Date, allDay: boolean) => {
      const initial = eventFormFromRange(start, end, activityTypes);
      initial.allDay = allDay;
      if (allDay) {
        const endInclusive = new Date(end);
        if (end.getTime() > start.getTime()) {
          endInclusive.setDate(endInclusive.getDate() - 1);
        }
        initial.endDate = endInclusive.toISOString().slice(0, 10);
      }
      setModalError(null);
      setModal({ kind: "create", initial });
    },
    [activityTypes]
  );

  const handleEventClick = useCallback(
    (eventId: string, anchor: DOMRect) => {
      const win = windowById.get(eventId);
      if (!win) return;
      openPopoverForWindow(win, anchor);
    },
    [windowById, openPopoverForWindow]
  );

  const handleReviewClick = useCallback(() => {
    const first = lowConfidenceToday[0];
    if (!first) return;
    const el = document.querySelector(`[data-event-id="${first.id}"]`);
    if (el instanceof HTMLElement) {
      el.scrollIntoView({ block: "center", behavior: "smooth" });
      openPopoverForWindow(first, el.getBoundingClientRect());
    } else {
      openPopoverForWindow(
        first,
        new DOMRect(200, 200, 1, 40)
      );
    }
  }, [lowConfidenceToday, openPopoverForWindow]);

  const handleEventChange = useCallback(
    async (change: CalendarEventChange) => {
      const win = windowById.get(change.id);
      if (!win || !windowIsEditable(win)) return;
      const segmentId = win.segment_ids[0];
      if (!segmentId) return;
      try {
        await updateSegment(segmentId, {
          started_at: change.start.toISOString(),
          ended_at: change.end.toISOString(),
          all_day: change.allDay,
        });
        if (range) await load(range.from, range.to);
        onDataChange?.();
      } catch (e) {
        setError(e instanceof Error ? e.message : "Failed to update event");
        if (range) await load(range.from, range.to);
      }
    },
    [windowById, range, load, onDataChange]
  );

  const handleSave = useCallback(
    async (values: EventFormValues) => {
      setSaving(true);
      setModalError(null);
      const { started_at, ended_at, all_day } = eventFormToIsoRange(values);
      try {
        await createSegment({
          started_at,
          ended_at,
          activity_type: values.activityType,
          title: values.title || null,
          all_day,
        });
        setModal({ kind: "closed" });
        if (range) await load(range.from, range.to);
        onDataChange?.();
      } catch (e) {
        setModalError(e instanceof Error ? e.message : "Failed to save event");
      } finally {
        setSaving(false);
      }
    },
    [range, load, onDataChange]
  );

  return (
    <div className={styles.root}>
      {showReviewBanner && (
        <div className={styles.reviewBanner} role="status">
          <span>
            ⚠ {lowConfidenceToday.length} activities today may be wrong
          </span>
          <button type="button" onClick={handleReviewClick}>
            Review →
          </button>
        </div>
      )}
      {toast && (
        <p className={styles.toast} onAnimationEnd={() => setToast(null)}>
          {toast}
        </p>
      )}
      {loading && <p className={styles.status}>Loading…</p>}
      {error && <p className={styles.error}>{error}</p>}
      {!error && range && windows.length === 0 && !loading && (
        <p className={styles.status}>
          No activities in this range. Sync sources or drag on the calendar to add an event.
        </p>
      )}
      <WeekCalendar
        timezone={timezone}
        events={events}
        onDatesChange={handleDatesChange}
        onSelectRange={handleSelectRange}
        onEventClick={handleEventClick}
        onEventChange={handleEventChange}
        renderEventContent={renderEventContent}
        highlightEventId={highlightEventId}
      />
      {selectedWindow && (
        <CorrectionPopover
          window={selectedWindow}
          activityTypes={activityTypes}
          allWindows={windows}
          timezone={timezone}
          open={popoverOpen}
          onOpenChange={(open) => {
            setPopoverOpen(open);
            if (!open) {
              setSelectedWindow(null);
              setHighlightEventId(null);
            }
          }}
          anchorPosition={anchorPosition}
          onConfirm={async (id) => {
            await corrections.confirmWindow(id);
            onDataChange?.();
          }}
          onDismiss={async (id) => {
            await corrections.dismissWindow(id);
            onDataChange?.();
          }}
          onCorrectType={async (id, slug) => {
            await corrections.correctWindowType(id, slug);
            onDataChange?.();
          }}
          onAddManual={async (data) => {
            await corrections.addManualWindow(data);
            onDataChange?.();
          }}
        />
      )}
      {modal.kind === "create" && (
        <EventModal
          mode="create"
          open
          initial={modal.initial}
          readOnly={false}
          activityTypes={activityTypes}
          saving={saving}
          error={modalError}
          onClose={() => setModal({ kind: "closed" })}
          onSave={handleSave}
        />
      )}
    </div>
  );
}
