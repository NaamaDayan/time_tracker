import { getActivityTypes } from "@/lib/api";
import type { ActivityType } from "@/lib/types";
import { RulesPageClient } from "./RulesPageClient";

export const dynamic = "force-dynamic";

export default async function RulesPage() {
  let activityTypes: ActivityType[] = [];
  let loadError: string | null = null;

  try {
    activityTypes = await getActivityTypes();
  } catch (e) {
    loadError = e instanceof Error ? e.message : "Could not reach API";
  }

  return (
    <RulesPageClient activityTypes={activityTypes} loadError={loadError} />
  );
}
