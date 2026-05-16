"use client";

import { useState } from "react";
import { Tabs } from "@/components/Tabs";
import type { ActivityType } from "@/lib/types";
import { AggregatedView } from "./AggregatedView";
import { CalendarView } from "./CalendarView";

const SUB_TABS = [
  { id: "calendar" as const, label: "Calendar view" },
  { id: "aggregated" as const, label: "Aggregated view" },
];

interface TimeTrackingPanelProps {
  timezone: string;
  activityTypes: ActivityType[];
  refreshKey: number;
}

export function TimeTrackingPanel({
  timezone,
  activityTypes,
  refreshKey,
}: TimeTrackingPanelProps) {
  const [subTab, setSubTab] = useState<"calendar" | "aggregated">("calendar");

  return (
    <div>
      <Tabs tabs={SUB_TABS} active={subTab} onChange={setSubTab} variant="sub" />
      {subTab === "calendar" && (
        <CalendarView
          timezone={timezone}
          activityTypes={activityTypes}
          refreshKey={refreshKey}
        />
      )}
      {subTab === "aggregated" && (
        <AggregatedView activityTypes={activityTypes} refreshKey={refreshKey} />
      )}
    </div>
  );
}
