"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import styles from "./WorkHoursRange.module.css";

interface WorkHoursRangeProps {
  startHour: number;
  endHour: number;
  onChange: (start: number, end: number) => void;
  minGap?: number;
}

function clampHour(h: number): number {
  return Math.max(0, Math.min(24, h));
}

function formatHour(h: number): string {
  return `${h}:00`;
}

export function WorkHoursRange({
  startHour,
  endHour,
  onChange,
  minGap = 1,
}: WorkHoursRangeProps) {
  const trackRef = useRef<HTMLDivElement>(null);
  const [dragging, setDragging] = useState<"start" | "end" | null>(null);

  const hourFromClientX = useCallback((clientX: number): number => {
    const track = trackRef.current;
    if (!track) return 0;
    const rect = track.getBoundingClientRect();
    const ratio = Math.max(0, Math.min(1, (clientX - rect.left) / rect.width));
    return Math.round(ratio * 24);
  }, []);

  useEffect(() => {
    if (!dragging) return;

    const onMove = (e: PointerEvent) => {
      const h = hourFromClientX(e.clientX);
      if (dragging === "start") {
        const nextStart = clampHour(Math.min(h, endHour - minGap));
        if (nextStart !== startHour) onChange(nextStart, endHour);
      } else {
        const nextEnd = clampHour(Math.max(h, startHour + minGap));
        if (nextEnd !== endHour) onChange(startHour, nextEnd);
      }
    };

    const onUp = () => setDragging(null);

    window.addEventListener("pointermove", onMove);
    window.addEventListener("pointerup", onUp);
    return () => {
      window.removeEventListener("pointermove", onMove);
      window.removeEventListener("pointerup", onUp);
    };
  }, [dragging, startHour, endHour, hourFromClientX, minGap, onChange]);

  const startPct = (startHour / 24) * 100;
  const endPct = (endHour / 24) * 100;

  return (
    <div className={styles.wrap}>
      <p className={styles.label}>Work hours</p>
      <div
        className={styles.track}
        ref={trackRef}
        role="group"
        aria-label={`Work hours ${formatHour(startHour)} to ${formatHour(endHour)}`}
      >
        <div
          className={styles.fill}
          style={{ left: `${startPct}%`, width: `${endPct - startPct}%` }}
        />
        <button
          type="button"
          className={styles.thumb}
          style={{ left: `${startPct}%` }}
          onPointerDown={(e) => {
            e.preventDefault();
            setDragging("start");
          }}
          aria-label={`Start ${formatHour(startHour)}`}
        />
        <button
          type="button"
          className={styles.thumb}
          style={{ left: `${endPct}%` }}
          onPointerDown={(e) => {
            e.preventDefault();
            setDragging("end");
          }}
          aria-label={`End ${formatHour(endHour)}`}
        />
      </div>
      <p className={styles.value}>
        {formatHour(startHour)} – {formatHour(endHour)}
      </p>
    </div>
  );
}
