"use client";

import dynamic from "next/dynamic";
import type { ActivityType } from "@/lib/types";
import styles from "./zones.module.css";

const ZoneMap = dynamic(
  () => import("@/components/zones/ZoneMap").then((mod) => mod.ZoneMap),
  { ssr: false, loading: () => <div className={styles.mapPlaceholder}>Loading map...</div> }
);

interface ZonesPageClientProps {
  activityTypes: ActivityType[];
  loadError: string | null;
}

export function ZonesPageClient({ activityTypes, loadError }: ZonesPageClientProps) {
  return (
    <main className={styles.main}>
      <header className={styles.header}>
        <h1>GPS zones</h1>
        <p className={styles.sub}>
          Double-click the map to add a zone. Click a zone to edit. Use the search bar on the map to find addresses.
        </p>
      </header>

      {loadError && (
        <div className={styles.banner} role="alert">
          <strong>API unavailable.</strong> {loadError}
        </div>
      )}

      <div className={styles.mapContainer}>
        <ZoneMap activityTypes={activityTypes} />
      </div>
    </main>
  );
}
