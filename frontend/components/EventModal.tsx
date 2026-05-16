"use client";

import { useEffect, useState } from "react";
import type { ActivityType } from "@/lib/types";
import styles from "./EventModal.module.css";

export interface EventFormValues {
  title: string;
  activityType: string;
  allDay: boolean;
  startDate: string;
  startTime: string;
  endDate: string;
  endTime: string;
}

interface EventModalProps {
  mode: "create" | "edit";
  open: boolean;
  initial: EventFormValues;
  activityTypes: ActivityType[];
  readOnly?: boolean;
  saving?: boolean;
  error?: string | null;
  onClose: () => void;
  onSave: (values: EventFormValues) => void;
  onDelete?: () => void;
}

function toLocalDateInput(iso: string): string {
  const d = new Date(iso);
  const y = d.getFullYear();
  const m = String(d.getMonth() + 1).padStart(2, "0");
  const day = String(d.getDate()).padStart(2, "0");
  return `${y}-${m}-${day}`;
}

function toLocalTimeInput(iso: string): string {
  const d = new Date(iso);
  const h = String(d.getHours()).padStart(2, "0");
  const min = String(d.getMinutes()).padStart(2, "0");
  return `${h}:${min}`;
}

export function eventFormFromRange(
  start: Date,
  end: Date,
  activityTypes: ActivityType[],
  title = ""
): EventFormValues {
  return {
    title,
    activityType: activityTypes[0]?.slug ?? "fun",
    allDay: false,
    startDate: toLocalDateInput(start.toISOString()),
    startTime: toLocalTimeInput(start.toISOString()),
    endDate: toLocalDateInput(end.toISOString()),
    endTime: toLocalTimeInput(end.toISOString()),
  };
}

export function eventFormFromSegment(
  seg: {
    started_at: string;
    ended_at: string;
    activity_type: string;
    metadata?: Record<string, unknown> | null;
  },
  allDay: boolean
): EventFormValues {
  const title =
    seg.metadata && typeof seg.metadata.title === "string"
      ? seg.metadata.title
      : seg.metadata && typeof seg.metadata.summary === "string"
        ? seg.metadata.summary
        : "";
  return {
    title,
    activityType: seg.activity_type,
    allDay,
    startDate: toLocalDateInput(seg.started_at),
    startTime: toLocalTimeInput(seg.started_at),
    endDate: toLocalDateInput(seg.ended_at),
    endTime: toLocalTimeInput(seg.ended_at),
  };
}

export function eventFormToIsoRange(values: EventFormValues): {
  started_at: string;
  ended_at: string;
  all_day: boolean;
} {
  if (values.allDay) {
    const started_at = new Date(`${values.startDate}T00:00:00`).toISOString();
    const ended_at = new Date(`${values.endDate}T23:59:59`).toISOString();
    return { started_at, ended_at, all_day: true };
  }
  const started_at = new Date(`${values.startDate}T${values.startTime}:00`).toISOString();
  const ended_at = new Date(`${values.endDate}T${values.endTime}:00`).toISOString();
  return { started_at, ended_at, all_day: false };
}

export function EventModal({
  mode,
  open,
  initial,
  activityTypes,
  readOnly = false,
  saving = false,
  error = null,
  onClose,
  onSave,
  onDelete,
}: EventModalProps) {
  const [form, setForm] = useState<EventFormValues>(initial);

  useEffect(() => {
    if (open) setForm(initial);
  }, [open, initial]);

  if (!open) return null;

  return (
    <div
      className={styles.backdrop}
      role="presentation"
      onClick={(e) => {
        if (e.target === e.currentTarget) onClose();
      }}
    >
      <div
        className={styles.dialog}
        role="dialog"
        aria-modal="true"
        aria-labelledby="event-modal-title"
        onClick={(e) => e.stopPropagation()}
      >
        <h2 id="event-modal-title" className={styles.title}>
          {readOnly ? "Event details" : mode === "create" ? "New event" : "Edit event"}
        </h2>

        {readOnly && (
          <p className={styles.hint}>
            Synced events from Clockify or Google Calendar cannot be edited here.
          </p>
        )}

        <div className={styles.field}>
          <label htmlFor="event-title">Title</label>
          <input
            id="event-title"
            value={form.title}
            disabled={readOnly || saving}
            onChange={(e) => setForm((f) => ({ ...f, title: e.target.value }))}
            placeholder="Optional"
          />
        </div>

        <div className={styles.field}>
          <label htmlFor="event-type">Activity</label>
          <select
            id="event-type"
            value={form.activityType}
            disabled={readOnly || saving}
            onChange={(e) => setForm((f) => ({ ...f, activityType: e.target.value }))}
          >
            {activityTypes.map((t) => (
              <option key={t.slug} value={t.slug}>
                {t.label}
              </option>
            ))}
          </select>
        </div>

        <div className={styles.checkRow}>
          <input
            id="event-allday"
            type="checkbox"
            checked={form.allDay}
            disabled={readOnly || saving}
            onChange={(e) => setForm((f) => ({ ...f, allDay: e.target.checked }))}
          />
          <label htmlFor="event-allday">All day</label>
        </div>

        <div className={styles.row}>
          <div className={styles.field}>
            <label htmlFor="event-start-date">Start date</label>
            <input
              id="event-start-date"
              type="date"
              value={form.startDate}
              disabled={readOnly || saving}
              onChange={(e) => setForm((f) => ({ ...f, startDate: e.target.value }))}
            />
          </div>
          {!form.allDay && (
            <div className={styles.field}>
              <label htmlFor="event-start-time">Start time</label>
              <input
                id="event-start-time"
                type="time"
                value={form.startTime}
                disabled={readOnly || saving}
                onChange={(e) => setForm((f) => ({ ...f, startTime: e.target.value }))}
              />
            </div>
          )}
        </div>

        <div className={styles.row}>
          <div className={styles.field}>
            <label htmlFor="event-end-date">End date</label>
            <input
              id="event-end-date"
              type="date"
              value={form.endDate}
              disabled={readOnly || saving}
              onChange={(e) => setForm((f) => ({ ...f, endDate: e.target.value }))}
            />
          </div>
          {!form.allDay && (
            <div className={styles.field}>
              <label htmlFor="event-end-time">End time</label>
              <input
                id="event-end-time"
                type="time"
                value={form.endTime}
                disabled={readOnly || saving}
                onChange={(e) => setForm((f) => ({ ...f, endTime: e.target.value }))}
              />
            </div>
          )}
        </div>

        {error && <p className={styles.error}>{error}</p>}

        <div className={styles.actions}>
          {mode === "edit" && onDelete && !readOnly && (
            <button type="button" className={styles.danger} disabled={saving} onClick={onDelete}>
              Delete
            </button>
          )}
          <button type="button" disabled={saving} onClick={onClose}>
            {readOnly ? "Close" : "Cancel"}
          </button>
          {!readOnly && (
            <button
              type="button"
              className={styles.primary}
              disabled={saving}
              onClick={() => onSave(form)}
            >
              {saving ? "Saving…" : "Save"}
            </button>
          )}
        </div>
      </div>
    </div>
  );
}
