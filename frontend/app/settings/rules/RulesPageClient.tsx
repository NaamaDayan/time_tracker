"use client";

import { ActivityRuleCard } from "@/components/rules/ActivityRuleCard";
import { useRuleConfigs } from "@/hooks/useRuleConfigs";
import type { ActivityType } from "@/lib/types";
import styles from "./rules.module.css";

interface RulesPageClientProps {
  activityTypes: ActivityType[];
  loadError: string | null;
}

export function RulesPageClient({ activityTypes, loadError }: RulesPageClientProps) {
  const { configs, loading, error, debouncedUpdate, savingSlug, savedSlug } =
    useRuleConfigs();

  const displayError = loadError ?? error;

  return (
    <main className={styles.main}>
      <header className={styles.header}>
        <h1>Activity rules</h1>
        <p className={styles.sub}>
          Tune how activities are detected. Changes save automatically.
        </p>
      </header>

      {displayError && (
        <div className={styles.banner} role="alert">
          <strong>API unavailable.</strong> {displayError}
        </div>
      )}

      {loading && <p className={styles.muted}>Loading rules…</p>}

      {!loading &&
        configs.map((config) => (
          <ActivityRuleCard
            key={config.activity_type_slug}
            config={config}
            activityTypes={activityTypes}
            onPatch={debouncedUpdate}
            saved={savedSlug === config.activity_type_slug}
            saving={savingSlug === config.activity_type_slug}
          />
        ))}
    </main>
  );
}
