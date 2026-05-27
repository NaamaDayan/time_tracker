"use client";

import { useEffect, useState } from "react";
import { previewRuleConfig } from "@/lib/api";
import type { PreviewResponse } from "@/lib/types";
import styles from "./PreviewPanel.module.css";

interface PreviewPanelProps {
  slug: string;
  onDismiss: () => void;
}

function formatTime(iso: string): string {
  try {
    return new Date(iso).toLocaleString(undefined, {
      month: "short",
      day: "numeric",
      hour: "2-digit",
      minute: "2-digit",
    });
  } catch {
    return iso;
  }
}

export function PreviewPanel({ slug, onDismiss }: PreviewPanelProps) {
  const [data, setData] = useState<PreviewResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setError(null);
    previewRuleConfig(slug)
      .then((res) => {
        if (!cancelled) setData(res);
      })
      .catch((e) => {
        if (!cancelled) {
          setError(e instanceof Error ? e.message : "Preview failed");
        }
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [slug]);

  const avgPerDay =
    data && data.segment_count > 0 ? (data.total_minutes / 7).toFixed(0) : "0";

  return (
    <div className={styles.panel}>
      {loading && <p className={styles.muted}>Loading preview…</p>}
      {error && <p className={styles.error}>{error}</p>}
      {data && !loading && (
        <>
          <p className={styles.summary}>
            Found <strong>{data.segment_count}</strong> sessions, ~
            <strong>{avgPerDay}</strong> min/day on average
          </p>
          {data.sample_segments.length > 0 ? (
            <ul className={styles.list}>
              {data.sample_segments.map((seg) => (
                <li key={seg.id}>
                  <span>{formatTime(seg.started_at)}</span>
                  <span className={styles.duration}>{seg.duration_minutes} min</span>
                </li>
              ))}
            </ul>
          ) : (
            <p className={styles.muted}>No segments in the last 7 days.</p>
          )}
          <p className={styles.question}>Does this look right?</p>
          <div className={styles.actions}>
            <button type="button" className={styles.okBtn} onClick={onDismiss}>
              ✓ Looks good
            </button>
            <button type="button" className={styles.adjustBtn} onClick={onDismiss}>
              ✗ Adjust
            </button>
          </div>
        </>
      )}
    </div>
  );
}
