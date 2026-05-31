"use client";

import * as Popover from "@radix-ui/react-popover";
import { useCallback, useMemo, useState } from "react";
import { resolveActivityDisplay } from "@/lib/activityRegistry";
import { CATEGORY_ORDER, groupActivitySlugs } from "@/lib/activityCategories";
import { confidenceLabel } from "@/lib/confidence";
import { windowTitle } from "@/lib/calendarEvents";
import type { ActivityType, ActivityWindow } from "@/lib/types";
import type { ManualWindowInput } from "@/lib/types";
import styles from "./CorrectionPopover.module.css";

const GAP_MIN_MS = 5 * 60 * 1000;

export interface AdjacentGap {
  side: "before" | "after";
  from: string;
  to: string;
}

function formatDurationMs(ms: number): string {
  const totalMin = Math.round(ms / 60000);
  const h = Math.floor(totalMin / 60);
  const m = totalMin % 60;
  if (h > 0 && m > 0) return `${h}h ${m}m`;
  if (h > 0) return `${h}h`;
  return `${m}m`;
}

function formatTimeRange(win: ActivityWindow, timezone: string): string {
  const opts: Intl.DateTimeFormatOptions = {
    hour: "2-digit",
    minute: "2-digit",
    timeZone: timezone,
  };
  const start = new Date(win.started_at);
  const end = new Date(win.ended_at);
  const a = start.toLocaleTimeString([], opts);
  const b = end.toLocaleTimeString([], opts);
  const dur = formatDurationMs(end.getTime() - start.getTime());
  return `${a} – ${b} (${dur})`;
}

function formatSourceList(sources: string[]): string {
  const labels: Record<string, string> = {
    activitywatch_desktop: "ActivityWatch Desktop",
    activitywatch: "Activity Watch",
    google_calendar: "Google Calendar",
    samsung_health: "Samsung Health",
    geofence: "GPS zone",
    dawarich: "Dawarich",
    manual: "Manual",
  };
  return sources.map((s) => labels[s] ?? s).join(", ");
}

export function findAdjacentGaps(
  win: ActivityWindow,
  allWindows: ActivityWindow[]
): AdjacentGap[] {
  const gaps: AdjacentGap[] = [];
  const sorted = [...allWindows]
    .filter((w) => !w.dismissed_by_user && w.id !== win.id)
    .sort(
      (a, b) => new Date(a.started_at).getTime() - new Date(b.started_at).getTime()
    );
  const winStart = new Date(win.started_at).getTime();
  const winEnd = new Date(win.ended_at).getTime();

  const beforeCandidates = sorted.filter(
    (w) => new Date(w.ended_at).getTime() <= winStart
  );
  if (beforeCandidates.length > 0) {
    const prev = beforeCandidates[beforeCandidates.length - 1]!;
    const prevEndTime = new Date(prev.ended_at).getTime();
    if (winStart - prevEndTime >= GAP_MIN_MS) {
      gaps.push({
        side: "before",
        from: new Date(prevEndTime).toISOString(),
        to: new Date(winStart).toISOString(),
      });
    }
  } else {
    const dayStart = new Date(win.started_at);
    dayStart.setHours(0, 0, 0, 0);
    if (winStart - dayStart.getTime() >= GAP_MIN_MS) {
      gaps.push({
        side: "before",
        from: dayStart.toISOString(),
        to: new Date(winStart).toISOString(),
      });
    }
  }

  const afterCandidates = sorted.filter(
    (w) => new Date(w.started_at).getTime() >= winEnd
  );
  if (afterCandidates.length > 0) {
    const next = afterCandidates[0]!;
    const nextStart = new Date(next.started_at).getTime();
    if (nextStart - winEnd >= GAP_MIN_MS) {
      gaps.push({
        side: "after",
        from: new Date(winEnd).toISOString(),
        to: new Date(nextStart).toISOString(),
      });
    }
  }

  return gaps;
}

function toLocalDatetimeInput(iso: string): string {
  const d = new Date(iso);
  const y = d.getFullYear();
  const mo = String(d.getMonth() + 1).padStart(2, "0");
  const day = String(d.getDate()).padStart(2, "0");
  const h = String(d.getHours()).padStart(2, "0");
  const min = String(d.getMinutes()).padStart(2, "0");
  return `${y}-${mo}-${day}T${h}:${min}`;
}

interface CorrectionPopoverProps {
  window: ActivityWindow;
  activityTypes: ActivityType[];
  allWindows: ActivityWindow[];
  timezone: string;
  open: boolean;
  onOpenChange: (open: boolean) => void;
  anchorPosition: { x: number; y: number } | null;
  onConfirm: (id: number) => Promise<void>;
  onDismiss: (id: number) => Promise<void>;
  onCorrectType: (id: number, slug: string) => Promise<void>;
  onAddManual: (data: ManualWindowInput) => Promise<void>;
}

export function CorrectionPopover({
  window: win,
  activityTypes,
  allWindows,
  timezone,
  open,
  onOpenChange,
  onConfirm,
  onDismiss,
  onCorrectType,
  onAddManual,
  anchorPosition,
}: CorrectionPopoverProps) {
  const [newSlug, setNewSlug] = useState(win.activity_type);
  const [busy, setBusy] = useState(false);
  const [gapOpen, setGapOpen] = useState(false);
  const [gapSlug, setGapSlug] = useState(activityTypes[0]?.slug ?? "work");
  const [gapFrom, setGapFrom] = useState("");
  const [gapTo, setGapTo] = useState("");
  const [localError, setLocalError] = useState<string | null>(null);

  const display = resolveActivityDisplay(win.activity_type, activityTypes);
  const title = windowTitle(win);
  const grouped = useMemo(
    () =>
      groupActivitySlugs(
        activityTypes.map((t) => t.slug),
        win.activity_type
      ),
    [activityTypes, win.activity_type]
  );
  const adjacentGaps = useMemo(
    () => findAdjacentGaps(win, allWindows),
    [win, allWindows]
  );

  const run = useCallback(
    async (fn: () => Promise<void>) => {
      setBusy(true);
      setLocalError(null);
      try {
        await fn();
        onOpenChange(false);
      } catch (e) {
        setLocalError(
          e instanceof Error ? e.message : "Couldn't save — try again"
        );
      } finally {
        setBusy(false);
      }
    },
    [onOpenChange]
  );

  const openGapForm = (gap: AdjacentGap) => {
    setGapFrom(toLocalDatetimeInput(gap.from));
    setGapTo(toLocalDatetimeInput(gap.to));
    setGapOpen(true);
  };

  if (!open || !anchorPosition) return null;

  return (
    <Popover.Root open={open} onOpenChange={onOpenChange}>
      <Popover.Anchor asChild>
        <span
          style={{
            position: "fixed",
            left: anchorPosition.x,
            top: anchorPosition.y,
            width: 1,
            height: 1,
            pointerEvents: "none",
          }}
        />
      </Popover.Anchor>
      <Popover.Portal>
        <Popover.Content className={styles.content} side="right" align="start" sideOffset={6}>
          <div className={styles.header}>
            {display.emoji} {title} • {formatTimeRange(win, timezone)}
          </div>
          <div className={styles.meta}>
            Source: {formatSourceList(win.sources)} • Confidence:{" "}
            {confidenceLabel(win)}
          </div>
          <hr className={styles.divider} />
          <div className={styles.actions}>
            <button
              type="button"
              disabled={busy || win.confirmed_by_user}
              onClick={() => run(() => onConfirm(win.id))}
            >
              ✓ Confirm
            </button>
            <button
              type="button"
              disabled={busy}
              onClick={() => run(() => onDismiss(win.id))}
            >
              ✗ Dismiss
            </button>
          </div>
          <div className={styles.field}>
            <label htmlFor="correct-type">Change to:</label>
            <select
              id="correct-type"
              value={newSlug}
              onChange={(e) => setNewSlug(e.target.value)}
              disabled={busy}
            >
              {CATEGORY_ORDER.map((cat) => {
                const slugs = grouped.get(cat) ?? [];
                if (slugs.length === 0) return null;
                return (
                  <optgroup key={cat} label={cat}>
                    {slugs.map((slug) => {
                      const d = resolveActivityDisplay(slug, activityTypes);
                      return (
                        <option key={slug} value={slug}>
                          {d.emoji} {d.label}
                        </option>
                      );
                    })}
                  </optgroup>
                );
              })}
            </select>
          </div>
          <div className={styles.applyRow}>
            <button
              type="button"
              disabled={busy || newSlug === win.activity_type}
              onClick={() => run(() => onCorrectType(win.id, newSlug))}
            >
              Apply change →
            </button>
          </div>
          {adjacentGaps.length > 0 && (
            <div className={styles.gapSection}>
              <hr className={styles.divider} />
              {!gapOpen ? (
                adjacentGaps.map((gap) => (
                  <button
                    key={gap.side}
                    type="button"
                    className={styles.gapToggle}
                    onClick={() => openGapForm(gap)}
                  >
                    + Add activity in adjacent gap ({gap.side})
                  </button>
                ))
              ) : (
                <div className={styles.gapForm}>
                  <div className={styles.field}>
                    <label>Type</label>
                    <select
                      value={gapSlug}
                      onChange={(e) => setGapSlug(e.target.value)}
                      disabled={busy}
                    >
                      {activityTypes.map((t) => (
                        <option key={t.slug} value={t.slug}>
                          {t.label}
                        </option>
                      ))}
                    </select>
                  </div>
                  <div className={styles.field}>
                    <label>From</label>
                    <input
                      type="datetime-local"
                      value={gapFrom}
                      onChange={(e) => setGapFrom(e.target.value)}
                      disabled={busy}
                    />
                  </div>
                  <div className={styles.field}>
                    <label>To</label>
                    <input
                      type="datetime-local"
                      value={gapTo}
                      onChange={(e) => setGapTo(e.target.value)}
                      disabled={busy}
                    />
                  </div>
                  <div className={styles.gapActions}>
                    <button
                      type="button"
                      disabled={busy}
                      onClick={() =>
                        run(async () => {
                          const from = new Date(gapFrom);
                          const to = new Date(gapTo);
                          await onAddManual({
                            activity_type_slug: gapSlug,
                            started_at: from.toISOString(),
                            ended_at: to.toISOString(),
                          });
                        })
                      }
                    >
                      Add ✓
                    </button>
                    <button
                      type="button"
                      disabled={busy}
                      onClick={() => setGapOpen(false)}
                    >
                      Cancel ✗
                    </button>
                  </div>
                </div>
              )}
            </div>
          )}
          {localError && <p className={styles.toast}>{localError}</p>}
          <Popover.Arrow />
        </Popover.Content>
      </Popover.Portal>
    </Popover.Root>
  );
}
