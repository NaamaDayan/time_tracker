import { AppShell } from "@/components/AppShell";
import { getActivityTypes, getConfig } from "@/lib/api";
import type { ActivityType } from "@/lib/types";

export const dynamic = "force-dynamic";

export default async function HomePage() {
  let timezone = "UTC";
  let activityTypes: ActivityType[] = [];
  let loadError: string | null = null;

  try {
    const config = await getConfig();
    timezone = config.timezone;
    activityTypes = await getActivityTypes();
  } catch (e) {
    loadError = e instanceof Error ? e.message : "Could not reach API";
  }

  return (
    <AppShell timezone={timezone} activityTypes={activityTypes} loadError={loadError} />
  );
}
