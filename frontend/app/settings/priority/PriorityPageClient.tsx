"use client";

import { useState } from "react";
import { PriorityRankList } from "@/components/priority/PriorityRankList";
import { useActivityPriority } from "@/hooks/useActivityPriority";
import type { ActivityType } from "@/lib/types";
import styles from "./priority.module.css";

interface PriorityPageClientProps {
  activityTypes: ActivityType[];
  loadError: string | null;
}

export function PriorityPageClient({ activityTypes, loadError }: PriorityPageClientProps) {
  const {
    itemsBySlug,
    localOrder,
    enabledBySlug,
    loading,
    saving,
    error,
    isDirty,
    savePriority,
    resetToDefaults,
    reorder,
  } = useActivityPriority();

  const [toast, setToast] = useState<{ kind: "success" | "error"; message: string } | null>(
    null
  );
  const [confirmReset, setConfirmReset] = useState(false);

  const displayError = loadError ?? error;

  async function handleSave() {
    const ok = await savePriority(localOrder);
    if (ok) {
      setToast({ kind: "success", message: "Priority order saved" });
    } else {
      setToast({ kind: "error", message: "Save failed — order not changed" });
    }
  }

  async function handleConfirmReset() {
    const defaults = resetToDefaults();
    reorder(defaults);
    setConfirmReset(false);
    const ok = await savePriority(defaults);
    if (ok) {
      setToast({ kind: "success", message: "Priority order saved" });
    } else {
      setToast({ kind: "error", message: "Save failed — order not changed" });
    }
  }

  return (
    <main className={styles.main}>
      <header className={styles.header}>
        <h1>Activity priority</h1>
        <p className={styles.sub}>
          When activities overlap, higher-ranked types win the pie chart slice.
        </p>
      </header>

      {displayError && !loading && (
        <div className={styles.banner} role="alert">
          <strong>API unavailable.</strong> {displayError}
        </div>
      )}

      <div className={styles.callout} role="note">
        ℹ When two activities overlap at the same moment, the one ranked higher here wins
        the pie chart slice. The full timeline always shows all activities.
      </div>

      {loading && <p className={styles.muted}>Loading priority…</p>}

      {!loading && localOrder.length > 0 && (
        <PriorityRankList
          localOrder={localOrder}
          enabledBySlug={enabledBySlug}
          itemsBySlug={itemsBySlug}
          activityTypes={activityTypes}
          onReorder={reorder}
        />
      )}

      <div className={styles.actions}>
        <button
          type="button"
          className={styles.destructiveBtn}
          onClick={() => setConfirmReset(true)}
          disabled={saving}
        >
          Reset to defaults
        </button>
      </div>

      {confirmReset && (
        <div className={styles.confirmBox}>
          Reset to defaults? This can&apos;t be undone
          <div className={styles.confirmActions}>
            <button
              type="button"
              className={styles.confirmBtn}
              onClick={() => setConfirmReset(false)}
            >
              Cancel
            </button>
            <button
              type="button"
              className={styles.confirmBtnDanger}
              onClick={handleConfirmReset}
              disabled={saving}
            >
              Confirm
            </button>
          </div>
        </div>
      )}

      {toast && (
        <p
          className={toast.kind === "success" ? styles.toastSuccess : styles.toastError}
          role="status"
        >
          {toast.message}
        </p>
      )}

      {isDirty && (
        <div className={styles.saveBar}>
          <button
            type="button"
            className={styles.primaryBtn}
            onClick={handleSave}
            disabled={saving}
          >
            {saving ? "Saving…" : "Save order"}
          </button>
        </div>
      )}
    </main>
  );
}
