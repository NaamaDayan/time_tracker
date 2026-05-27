"use client";

import { useState } from "react";
import Link from "next/link";
import { Tabs } from "@/components/Tabs";
import { GoogleCalendarConnect } from "@/components/GoogleCalendarConnect";
import { SyncButton } from "@/components/SyncButton";
import { HabitsPanel } from "@/components/habits/HabitsPanel";
import { TimeTrackingPanel } from "@/components/time-tracking/TimeTrackingPanel";
import type { ActivityType } from "@/lib/types";
import styles from "./AppShell.module.css";

const MAIN_TABS = [
  { id: "time" as const, label: "Time tracking" },
  { id: "habits" as const, label: "Habit tracking" },
];

interface AppShellProps {
  timezone: string;
  activityTypes: ActivityType[];
  loadError: string | null;
}

export function AppShell({ timezone, activityTypes, loadError }: AppShellProps) {
  const [mainTab, setMainTab] = useState<"time" | "habits">("time");
  const [refreshKey, setRefreshKey] = useState(0);

  return (
    <main className={styles.main}>
      <header className={styles.header}>
        <div>
          <h1>Time Tracker</h1>
          <p className={styles.sub}>Personal activity timeline</p>
        </div>
        <div className={styles.headerActions}>
          <GoogleCalendarConnect />
          <SyncButton onSynced={() => setRefreshKey((k) => k + 1)} />
          <Link href="/settings" className={styles.settingsLink} title="Settings">
            <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden>
              <circle cx="12" cy="12" r="3" />
              <path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 0 1-2.83 2.83l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 0 1-4 0v-.09A1.65 1.65 0 0 0 9 19.4a1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 0 1-2.83-2.83l.06-.06A1.65 1.65 0 0 0 4.68 15a1.65 1.65 0 0 0-1.51-1H3a2 2 0 0 1 0-4h.09A1.65 1.65 0 0 0 4.6 9a1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 0 1 2.83-2.83l.06.06A1.65 1.65 0 0 0 9 4.68a1.65 1.65 0 0 0 1-1.51V3a2 2 0 0 1 4 0v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 0 1 2.83 2.83l-.06.06A1.65 1.65 0 0 0 19.4 9a1.65 1.65 0 0 0 1.51 1H21a2 2 0 0 1 0 4h-.09a1.65 1.65 0 0 0-1.51 1z" />
            </svg>
          </Link>
        </div>
      </header>

      {loadError && (
        <div className={styles.banner} role="alert">
          <strong>API unavailable.</strong> {loadError}. Start Postgres and the backend (see
          README).
        </div>
      )}

      <Tabs tabs={MAIN_TABS} active={mainTab} onChange={setMainTab} variant="main" />

      {mainTab === "time" && (
        <TimeTrackingPanel
          timezone={timezone}
          activityTypes={activityTypes}
          refreshKey={refreshKey}
        />
      )}
      {mainTab === "habits" && <HabitsPanel />}
    </main>
  );
}
