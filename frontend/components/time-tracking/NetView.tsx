"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { getNet } from "@/lib/api";
import { rangeForPreset } from "@/lib/dateRange";
import type { ActivityType, NetResponse, TimeWindowPreset } from "@/lib/types";
import styles from "./NetView.module.css";

const PRESETS: { id: TimeWindowPreset; label: string }[] = [
  { id: "day", label: "Day" },
  { id: "week", label: "Week" },
  { id: "month", label: "Month" },
  { id: "year", label: "Year" },
  { id: "custom", label: "Custom range" },
];

function formatDuration(seconds: number): string {
  const h = Math.floor(seconds / 3600);
  const m = Math.round((seconds % 3600) / 60);
  if (h > 0) return `${h}h ${m}m`;
  return `${m}m`;
}

interface NetViewProps {
  activityTypes: ActivityType[];
  refreshKey: number;
}

export function NetView({ activityTypes, refreshKey }: NetViewProps) {
  const [preset, setPreset] = useState<TimeWindowPreset>("week");
  const [customFrom, setCustomFrom] = useState("");
  const [customTo, setCustomTo] = useState("");
  const [selectedTypes, setSelectedTypes] = useState<Set<string>>(
    () => new Set(activityTypes.map((t) => t.slug))
  );
  const [data, setData] = useState<NetResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    setSelectedTypes((prev) => {
      const next = new Set(prev);
      for (const t of activityTypes) {
        if (![...next].some((s) => activityTypes.find((a) => a.slug === s))) {
          next.add(t.slug);
        }
      }
      if (next.size === 0) {
        return new Set(activityTypes.map((t) => t.slug));
      }
      return next;
    });
  }, [activityTypes]);

  const selectedTypesKey = useMemo(
    () => [...selectedTypes].sort().join(","),
    [selectedTypes]
  );

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const { from, to } = rangeForPreset(
        preset,
        customFrom || undefined,
        customTo || undefined
      );
      const types = selectedTypesKey ? selectedTypesKey.split(",") : undefined;
      const result = await getNet(from.toISOString(), to.toISOString(), types);
      setData(result);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to load net totals");
      setData(null);
    } finally {
      setLoading(false);
    }
  }, [preset, customFrom, customTo, selectedTypesKey]);

  useEffect(() => {
    load();
  }, [load, refreshKey]);

  function toggleType(slug: string) {
    setSelectedTypes((prev) => {
      const next = new Set(prev);
      if (next.has(slug)) {
        if (next.size > 1) next.delete(slug);
      } else {
        next.add(slug);
      }
      return next;
    });
  }

  const rangeLabel = rangeForPreset(
    preset,
    customFrom || undefined,
    customTo || undefined
  ).label;

  return (
    <div className={styles.root}>
      <div className={styles.filters}>
        <fieldset className={styles.fieldset}>
          <legend>Time window</legend>
          <div className={styles.presetRow}>
            {PRESETS.map((p) => (
              <label key={p.id} className={styles.radio}>
                <input
                  type="radio"
                  name="net-preset"
                  checked={preset === p.id}
                  onChange={() => setPreset(p.id)}
                />
                {p.label}
              </label>
            ))}
          </div>
          {preset === "custom" && (
            <div className={styles.customRange}>
              <label>
                From
                <input
                  type="date"
                  value={customFrom}
                  onChange={(e) => setCustomFrom(e.target.value)}
                />
              </label>
              <label>
                To
                <input
                  type="date"
                  value={customTo}
                  onChange={(e) => setCustomTo(e.target.value)}
                />
              </label>
            </div>
          )}
        </fieldset>

        <fieldset className={styles.fieldset}>
          <legend>Activity types</legend>
          <div className={styles.typeGrid}>
            {activityTypes.map((t) => (
              <label key={t.slug} className={styles.check}>
                <input
                  type="checkbox"
                  checked={selectedTypes.has(t.slug)}
                  onChange={() => toggleType(t.slug)}
                />
                <span className={styles.typeSwatch} style={{ background: t.color }} />
                {t.label}
              </label>
            ))}
          </div>
        </fieldset>

        <button type="button" className={styles.apply} onClick={load} disabled={loading}>
          {loading ? "Loading…" : "Apply"}
        </button>
      </div>

      <p className={styles.hint}>
        Net minutes per activity type; overlapping activities are counted separately (can exceed
        24h per day).
      </p>
      <p className={styles.range}>{rangeLabel}</p>

      {error && <p className={styles.error}>{error}</p>}
      {data && !loading && (
        <div className={styles.results}>
          <p className={styles.summary}>
            Total tracked: {formatDuration(data.total_seconds)}
            {data.calendar_days > 1 && ` · ${data.calendar_days} days`}
          </p>
          {data.slices.length === 0 ? (
            <p className={styles.empty}>No activity in this range for the selected types.</p>
          ) : (
            <table className={styles.table}>
              <thead>
                <tr>
                  <th>Activity</th>
                  <th>Time</th>
                  <th>% of net total</th>
                </tr>
              </thead>
              <tbody>
                {data.slices.map((row) => (
                  <tr key={row.activity_type}>
                    <td>
                      <span className={styles.typeSwatch} style={{ background: row.color }} />
                      {row.label}
                    </td>
                    <td>{formatDuration(row.seconds)}</td>
                    <td>{row.percent}%</td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </div>
      )}
    </div>
  );
}
