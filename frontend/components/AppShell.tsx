"use client";

import { useState } from "react";
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
