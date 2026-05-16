"use client";

import { useCallback, useEffect, useState } from "react";
import { getGoogleCalendarStatus } from "@/lib/api";
import styles from "./GoogleCalendarConnect.module.css";

const BACKEND_URL =
  process.env.NEXT_PUBLIC_BACKEND_URL ?? "http://localhost:8000";

export function GoogleCalendarConnect() {
  const [connected, setConnected] = useState<boolean | null>(null);
  const [email, setEmail] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  const refresh = useCallback(async () => {
    setLoading(true);
    try {
      const status = await getGoogleCalendarStatus();
      setConnected(status.connected);
      setEmail(status.email ?? null);
    } catch {
      setConnected(false);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    refresh();
    const params = new URLSearchParams(window.location.search);
    if (params.get("google_connected") === "1") {
      refresh();
      const url = new URL(window.location.href);
      url.searchParams.delete("google_connected");
      window.history.replaceState({}, "", url.pathname + url.search);
    }
  }, [refresh]);

  function handleConnect() {
    window.location.href = `${BACKEND_URL}/api/v1/integrations/google/auth`;
  }

  if (loading) {
    return <span className={styles.muted}>Google Calendar…</span>;
  }

  if (connected) {
    return (
      <span className={styles.connected}>
        Google Calendar connected{email ? ` (${email})` : ""}
      </span>
    );
  }

  return (
    <button type="button" onClick={handleConnect} className={styles.btn}>
      Connect Google Calendar
    </button>
  );
}
