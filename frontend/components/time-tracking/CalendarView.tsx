"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import {
  EventModal,
  eventFormFromRange,
  eventFormToIsoRange,
  type EventFormValues,
} from "@/components/EventModal";
import { WeekCalendar, type CalendarEventChange } from "@/components/WeekCalendar";
import {
  createSegment,
  deleteSegment,
  getWindows,
  updateSegment,
} from "@/lib/api";
import {
  windowIsEditable,
  windowsToCalendarEvents,
} from "@/lib/calendarEvents";
import type { ActivityType, ActivityWindow } from "@/lib/types";
import styles from "./CalendarView.module.css";

interface CalendarViewProps {
  timezone: string;
  activityTypes: ActivityType[];
  refreshKey: number;
  onDataChange?: () => void;
}

type ModalState =
  | { kind: "closed" }
  | { kind: "create"; initial: EventFormValues }
  | {
      kind: "edit";
      window: ActivityWindow;
      segmentId: number | null;
      readOnly: boolean;
      initial: EventFormValues;
    };

function eventFormFromWindow(win: ActivityWindow, allDay: boolean): EventFormValues {
  const start = new Date(win.started_at);
  const end = new Date(win.ended_at);
  const toLocalDateInput = (d: Date) => {
    const y = d.getFullYear();
    const m = String(d.getMonth() + 1).padStart(2, "0");
    const day = String(d.getDate()).padStart(2, "0");
    return `${y}-${m}-${day}`;
  };
  const toLocalTimeInput = (d: Date) => {
    const h = String(d.getHours()).padStart(2, "0");
    const min = String(d.getMinutes()).padStart(2, "0");
    return `${h}:${min}`;
  };
  return {
    title: "",
    activityType: win.activity_type,
    allDay,
    startDate: toLocalDateInput(start),
    startTime: toLocalTimeInput(start),
    endDate: toLocalDateInput(end),
    endTime: toLocalTimeInput(end),
  };
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
  const [modal, setModal] = useState<ModalState>({ kind: "closed" });
  const [modalError, setModalError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);

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

  const events = useMemo(
    () => windowsToCalendarEvents(windows, timezone),
    [windows, timezone]
  );

  const windowById = useMemo(() => {
    const map = new Map<string, ActivityWindow>();
    for (const win of windows) map.set(String(win.id), win);
    return map;
  }, [windows]);

  const closeModal = useCallback(() => {
    setModal({ kind: "closed" });
    setModalError(null);
  }, []);

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
    (eventId: string) => {
      const win = windowById.get(eventId);
      if (!win) return;
      const allDay = windowIsAllDay(win);
      const editable = windowIsEditable(win);
      const segmentId = editable ? win.segment_ids[0]! : null;
      setModalError(null);
      setModal({
        kind: "edit",
        window: win,
        segmentId,
        readOnly: !editable,
        initial: eventFormFromWindow(win, allDay),
      });
    },
    [windowById]
  );

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
        if (modal.kind === "create") {
          await createSegment({
            started_at,
            ended_at,
            activity_type: values.activityType,
            title: values.title || null,
            all_day,
          });
        } else if (modal.kind === "edit" && modal.segmentId != null) {
          await updateSegment(modal.segmentId, {
            started_at,
            ended_at,
            activity_type: values.activityType,
            title: values.title || null,
            all_day,
          });
        }
        closeModal();
        if (range) await load(range.from, range.to);
        onDataChange?.();
      } catch (e) {
        setModalError(e instanceof Error ? e.message : "Failed to save event");
      } finally {
        setSaving(false);
      }
    },
    [modal, closeModal, range, load, onDataChange]
  );

  const handleDelete = useCallback(async () => {
    if (modal.kind !== "edit" || modal.readOnly || modal.segmentId == null) return;
    if (!window.confirm("Delete this event?")) return;
    setSaving(true);
    setModalError(null);
    try {
      await deleteSegment(modal.segmentId);
      closeModal();
      if (range) await load(range.from, range.to);
      onDataChange?.();
    } catch (e) {
      setModalError(e instanceof Error ? e.message : "Failed to delete event");
    } finally {
      setSaving(false);
    }
  }, [modal, closeModal, range, load, onDataChange]);

  const modalProps =
    modal.kind === "closed"
      ? null
      : {
          mode: modal.kind as "create" | "edit",
          open: true,
          initial: modal.initial,
          readOnly: modal.kind === "edit" ? modal.readOnly : false,
          onDelete: modal.kind === "edit" && !modal.readOnly ? handleDelete : undefined,
        };

  return (
    <div className={styles.root}>
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
      />
      {modalProps && (
        <EventModal
          {...modalProps}
          activityTypes={activityTypes}
          saving={saving}
          error={modalError}
          onClose={closeModal}
          onSave={handleSave}
        />
      )}
    </div>
  );
}
