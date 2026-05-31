import { getActivityTypes } from "@/lib/api";
import type { ActivityType } from "@/lib/types";
import { PriorityPageClient } from "./PriorityPageClient";

export const dynamic = "force-dynamic";

export default async function PriorityPage() {
  let activityTypes: ActivityType[] = [];
  let loadError: string | null = null;

  try {
    activityTypes = await getActivityTypes();
  } catch (e) {
    loadError = e instanceof Error ? e.message : "Could not reach API";
  }

  return <PriorityPageClient activityTypes={activityTypes} loadError={loadError} />;
}
