"use client";

import type { AggregateSlice } from "@/lib/types";
import styles from "./PieChart.module.css";

function formatDuration(seconds: number): string {
  const h = Math.floor(seconds / 3600);
  const m = Math.round((seconds % 3600) / 60);
  if (h > 0) return `${h}h ${m}m`;
  return `${m}m`;
}

function slicePath(
  cx: number,
  cy: number,
  r: number,
  startAngle: number,
  endAngle: number
): string {
  const x1 = cx + r * Math.cos(startAngle);
  const y1 = cy + r * Math.sin(startAngle);
  const x2 = cx + r * Math.cos(endAngle);
  const y2 = cy + r * Math.sin(endAngle);
  const large = endAngle - startAngle > Math.PI ? 1 : 0;
  return `M ${cx} ${cy} L ${x1} ${y1} A ${r} ${r} 0 ${large} 1 ${x2} ${y2} Z`;
}

interface PieChartProps {
  slices: AggregateSlice[];
  totalSeconds: number;
  unattributedSeconds?: number;
}

const UNATTRIBUTED_COLOR = "#3f3f46";

function round(n: number, digits: number) {
  const p = 10 ** digits;
  return Math.round(n * p) / p;
}

export function PieChart({ slices, totalSeconds, unattributedSeconds = 0 }: PieChartProps) {
  if (totalSeconds <= 0) {
    return <p className={styles.empty}>No activity in this range for the selected types.</p>;
  }

  const chartSlices =
    unattributedSeconds > 0
      ? [
          ...slices,
          {
            activity_type: "__unattributed",
            label: "Unattributed",
            color: UNATTRIBUTED_COLOR,
            seconds: unattributedSeconds,
            percent: round((100 * unattributedSeconds) / totalSeconds, 2),
          },
        ]
      : slices;

  const cx = 120;
  const cy = 120;
  const r = 100;
  let angle = -Math.PI / 2;

  const paths = chartSlices.map((slice) => {
    const sweep = (slice.seconds / totalSeconds) * Math.PI * 2;
    const start = angle;
    angle += sweep;
    return {
      ...slice,
      d: slicePath(cx, cy, r, start, angle),
    };
  });

  return (
    <div className={styles.wrap}>
      <svg viewBox="0 0 240 240" className={styles.chart} aria-label="Activity breakdown">
        {paths.map((p) => (
          <path key={p.activity_type} d={p.d} fill={p.color} stroke="var(--bg)" strokeWidth={1}>
            <title>
              {p.label}: {formatDuration(p.seconds)} ({p.percent}%)
            </title>
          </path>
        ))}
      </svg>
      <ul className={styles.legend}>
        {paths.map((p) => (
          <li key={p.activity_type}>
            <span className={styles.swatch} style={{ background: p.color }} />
            <span className={styles.legendLabel}>{p.label}</span>
            <span className={styles.legendMeta}>
              {formatDuration(p.seconds)} · {p.percent}%
            </span>
          </li>
        ))}
      </ul>
    </div>
  );
}
