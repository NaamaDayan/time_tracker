"use client";

import { useState } from "react";
import {
  formatActivityRecipe,
  resolveActivityDisplay,
} from "@/lib/activityRegistry";
import type {
  ActivityRuleConfig,
  ActivityRuleConfigUpdateInput,
  ActivityType,
} from "@/lib/types";
import { PreviewPanel } from "./PreviewPanel";
import { WorkHoursRange } from "./WorkHoursRange";
import styles from "./ActivityRuleCard.module.css";

const DAY_LABELS = ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"];

interface ActivityRuleCardProps {
  config: ActivityRuleConfig;
  activityTypes: ActivityType[];
  onPatch: (slug: string, patch: ActivityRuleConfigUpdateInput) => void;
  saved: boolean;
  saving: boolean;
}

export function ActivityRuleCard({
  config,
  activityTypes,
  onPatch,
  saved,
  saving,
}: ActivityRuleCardProps) {
  const [previewOpen, setPreviewOpen] = useState(false);
  const slug = config.activity_type_slug;
  const maxDuration =
    typeof config.custom_params.max_duration_minutes === "number"
      ? config.custom_params.max_duration_minutes
      : 15;

  const display = resolveActivityDisplay(slug, activityTypes);
  const recipe = formatActivityRecipe(
    slug,
    config.min_duration_minutes,
    activityTypes,
    maxDuration
  );

  const patch = (p: ActivityRuleConfigUpdateInput) => onPatch(slug, p);

  const toggleBoost = (key: string, value: boolean) => {
    patch({ boost_signals: { ...config.boost_signals, [key]: value } });
  };

  const setCustomParam = (key: string, value: unknown) => {
    patch({ custom_params: { ...config.custom_params, [key]: value } });
  };

  const workDays = Array.isArray(config.custom_params.work_days)
    ? (config.custom_params.work_days as number[])
    : [0, 1, 2, 3, 4, 5, 6];

  const toggleWorkDay = (day: number) => {
    const next = workDays.includes(day)
      ? workDays.filter((d) => d !== day)
      : [...workDays, day].sort((a, b) => a - b);
    setCustomParam("work_days", next);
  };

  return (
    <article className={`${styles.card} ${!config.enabled ? styles.disabled : ""}`}>
      <header className={styles.cardHeader}>
        <div className={styles.titleRow}>
          <span className={styles.emoji}>{display.emoji}</span>
          <h2>{display.label}</h2>
        </div>
        <label className={styles.toggle}>
          <input
            type="checkbox"
            checked={config.enabled}
            onChange={(e) => patch({ enabled: e.target.checked })}
          />
          <span className={styles.toggleUi} />
        </label>
      </header>

      <p className={styles.recipe}>
        <span className={styles.recipeLabel}>Fires when:</span> {recipe}
      </p>

      <div className={styles.sliderRow}>
        <label htmlFor={`${slug}-min`}>Minimum duration</label>
        <input
          id={`${slug}-min`}
          type="range"
          min={1}
          max={slug === "sleep" ? 360 : 120}
          value={config.min_duration_minutes}
          onChange={(e) =>
            patch({ min_duration_minutes: Number(e.target.value) })
          }
        />
        <span className={styles.value}>{config.min_duration_minutes} min</span>
      </div>

      <div className={styles.sliderRow}>
        <label htmlFor={`${slug}-gap`}>Session gap</label>
        <input
          id={`${slug}-gap`}
          type="range"
          min={0}
          max={120}
          value={config.merge_gap_minutes}
          onChange={(e) => patch({ merge_gap_minutes: Number(e.target.value) })}
        />
        <span className={styles.value}>{config.merge_gap_minutes} min</span>
      </div>

      {slug === "work" && (
        <div className={styles.extra}>
          <p className={styles.extraLabel}>Work days</p>
          <div className={styles.pills}>
            {DAY_LABELS.map((label, day) => (
              <button
                key={label}
                type="button"
                className={`${styles.pill} ${workDays.includes(day) ? styles.pillActive : ""}`}
                onClick={() => toggleWorkDay(day)}
              >
                {label}
              </button>
            ))}
          </div>
          <WorkHoursRange
            startHour={Number(config.custom_params.work_hours_start ?? 8)}
            endHour={Number(config.custom_params.work_hours_end ?? 20)}
            onChange={(start, end) => {
              patch({
                custom_params: {
                  ...config.custom_params,
                  work_hours_start: start,
                  work_hours_end: end,
                },
              });
            }}
          />
        </div>
      )}

      {slug === "sport" && (
        <div className={styles.extra}>
          <label className={styles.checkRow}>
            <input
              type="checkbox"
              checked={!!config.boost_signals.watch_active}
              onChange={(e) => toggleBoost("watch_active", e.target.checked)}
            />
            Boost confidence if Watch shows active time
          </label>
          <label className={styles.checkRow}>
            <input
              type="checkbox"
              checked={!!config.boost_signals.hevy_open}
              onChange={(e) => toggleBoost("hevy_open", e.target.checked)}
            />
            Boost confidence if Hevy app is open on phone
          </label>
        </div>
      )}

      {slug === "sleep" && (
        <div className={styles.extra}>
          <label className={styles.checkRow}>
            <input
              type="checkbox"
              checked={!!config.boost_signals.watch_confirmed}
              onChange={(e) => toggleBoost("watch_confirmed", e.target.checked)}
            />
            Use Samsung Watch as primary source
          </label>
          <label className={styles.checkRow}>
            <input
              type="checkbox"
              checked={
                config.custom_params.enable_screen_off_fallback !== false
              }
              onChange={(e) =>
                setCustomParam("enable_screen_off_fallback", e.target.checked)
              }
            />
            Enable screen-off fallback
          </label>
        </div>
      )}

      {slug === "bathroom" && (
        <div className={styles.sliderRow}>
          <label htmlFor={`${slug}-max`}>Max duration (flag longer)</label>
          <input
            id={`${slug}-max`}
            type="range"
            min={2}
            max={30}
            value={maxDuration}
            onChange={(e) =>
              setCustomParam("max_duration_minutes", Number(e.target.value))
            }
          />
          <span className={styles.value}>{maxDuration} min</span>
        </div>
      )}

      <footer className={styles.footer}>
        <button
          type="button"
          className={styles.previewBtn}
          onClick={() => setPreviewOpen((o) => !o)}
        >
          Preview last 7 days ↗
        </button>
        {(saved || saving) && (
          <span className={styles.saved}>{saving ? "Saving…" : "Saved"}</span>
        )}
      </footer>

      {previewOpen && (
        <PreviewPanel slug={slug} onDismiss={() => setPreviewOpen(false)} />
      )}
    </article>
  );
}
