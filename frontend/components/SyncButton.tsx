"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";
import { syncSources } from "@/lib/api";
import styles from "./SyncButton.module.css";

interface SyncButtonProps {
  onSynced?: () => void;
}

export function SyncButton({ onSynced }: SyncButtonProps) {
  const router = useRouter();
  const [loading, setLoading] = useState(false);
  const [message, setMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  async function handleSync() {
    setLoading(true);
    setMessage(null);
    setError(null);
    try {
      const result = await syncSources("7d");
      const parts = Object.entries(result.sources).map(([name, s]) => {
        const mode = (s as { mode?: string }).mode;
        const suffix = mode ? ` (${mode})` : "";
        return `${name}: ${s.entries_fetched ?? 0} entries${suffix}`;
      });
      const errParts = Object.entries(result.errors).map(([name, msg]) => `${name}: ${msg}`);
      if (errParts.length) {
        setError(errParts.join("; "));
      }
      setMessage(
        parts.length
          ? `${parts.join(" · ")} → ${result.segments_written} segments`
          : `Synced → ${result.segments_written} segments`
      );
      onSynced?.();
      router.refresh();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Sync failed");
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className={styles.wrap}>
      <button type="button" onClick={handleSync} disabled={loading} className={styles.btn}>
        {loading ? "Syncing…" : "Sync sources"}
      </button>
      {message && <p className={styles.ok}>{message}</p>}
      {error && <p className={styles.err}>{error}</p>}
    </div>
  );
}
