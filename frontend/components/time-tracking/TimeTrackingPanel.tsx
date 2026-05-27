"use client";

import { useState } from "react";
import { Tabs } from "@/components/Tabs";
import type { ActivityType } from "@/lib/types";
import { CalendarView } from "./CalendarView";
import { NetView } from "./NetView";
import { PieChartView } from "./PieChartView";

const SUB_TABS = [
  { id: "calendar" as const, label: "Calendar view" },
  { id: "pie-chart" as const, label: "Pie chart view" },
  { id: "net" as const, label: "Net view" },
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
  const [subTab, setSubTab] = useState<"calendar" | "pie-chart" | "net">("calendar");

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
      {subTab === "pie-chart" && (
        <PieChartView activityTypes={activityTypes} refreshKey={refreshKey} />
      )}
      {subTab === "net" && (
        <NetView activityTypes={activityTypes} refreshKey={refreshKey} />
      )}
    </div>
  );
}
