"use client";

import type { ActivityWindow } from "@/lib/types";
import {
  confidenceDotPulse,
  showConfidenceDot,
  windowOpacity,
} from "@/lib/confidence";
import styles from "./ActivityBlock.module.css";

interface ActivityBlockProps {
  window: ActivityWindow;
  title: string;
}

export function ActivityBlock({ window: win, title }: ActivityBlockProps) {
  const opacity = windowOpacity(win);
  const dot = showConfidenceDot(win);
  const pulse = confidenceDotPulse(win);

  return (
    <div className={styles.block} style={{ opacity }}>
      <div className={styles.title}>{title}</div>
      {win.confirmed_by_user ? (
        <span className={styles.check} aria-hidden>
          ✓
        </span>
      ) : dot ? (
        <span
          className={`${styles.indicator} ${pulse ? styles.indicatorPulse : ""}`}
          aria-hidden
        />
      ) : null}
    </div>
  );
}
