import { getActivityTypes } from "@/lib/api";
import type { ActivityType } from "@/lib/types";
import { ZonesPageClient } from "./ZonesPageClient";

export const dynamic = "force-dynamic";

export default async function ZonesPage() {
  let activityTypes: ActivityType[] = [];
  let loadError: string | null = null;

  try {
    activityTypes = await getActivityTypes();
  } catch (e) {
    loadError = e instanceof Error ? e.message : "Could not reach API";
  }

  return <ZonesPageClient activityTypes={activityTypes} loadError={loadError} />;
}
