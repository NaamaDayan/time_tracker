"use client";

import { useCallback, useRef } from "react";
import {
  createManualWindow,
  deleteManualWindow,
  patchWindow,
} from "@/lib/api";
import type { ActivityWindow, ManualWindowInput } from "@/lib/types";

interface UseWindowCorrectionsOptions {
  windows: ActivityWindow[];
  setWindows: React.Dispatch<React.SetStateAction<ActivityWindow[]>>;
  refetchRange: (from: Date, to: Date) => Promise<void>;
  range: { from: Date; to: Date } | null;
  onError?: (message: string) => void;
}

export function useWindowCorrections({
  windows,
  setWindows,
  refetchRange,
  range,
  onError,
}: UseWindowCorrectionsOptions) {
  const snapshotRef = useRef<ActivityWindow[] | null>(null);

  const revert = useCallback(() => {
    if (snapshotRef.current) {
      setWindows(snapshotRef.current);
      snapshotRef.current = null;
    }
  }, [setWindows]);

  const fail = useCallback(
    (err: unknown) => {
      revert();
      onError?.(err instanceof Error ? err.message : "Couldn't save — try again");
    },
    [revert, onError]
  );

  const snapshot = useCallback(() => {
    snapshotRef.current = windows;
  }, [windows]);

  const clearSnapshot = useCallback(() => {
    snapshotRef.current = null;
  }, []);

  const refetchDay = useCallback(
    async (isoDate: string) => {
      if (!range) return;
      const day = new Date(isoDate);
      const from = new Date(day);
      from.setHours(0, 0, 0, 0);
      const to = new Date(day);
      to.setHours(23, 59, 59, 999);
      await refetchRange(from, to);
    },
    [range, refetchRange]
  );

  const confirmWindow = useCallback(
    async (windowId: number): Promise<ActivityWindow> => {
      snapshot();
      setWindows((prev) =>
        prev.map((w) =>
          w.id === windowId ? { ...w, confirmed_by_user: true, confidence: w.confidence } : w
        )
      );
      try {
        const updated = await patchWindow(windowId, { confirmed_by_user: true });
        setWindows((prev) => prev.map((w) => (w.id === windowId ? updated : w)));
        clearSnapshot();
        return updated;
      } catch (e) {
        fail(e);
        throw e;
      }
    },
    [snapshot, setWindows, clearSnapshot, fail]
  );

  const dismissWindow = useCallback(
    async (windowId: number): Promise<void> => {
      snapshot();
      setWindows((prev) => prev.filter((w) => w.id !== windowId));
      try {
        await patchWindow(windowId, { dismissed_by_user: true });
        clearSnapshot();
      } catch (e) {
        fail(e);
        throw e;
      }
    },
    [snapshot, setWindows, clearSnapshot, fail]
  );

  const correctWindowType = useCallback(
    async (windowId: number, newSlug: string): Promise<ActivityWindow> => {
      const original = windows.find((w) => w.id === windowId);
      if (!original) throw new Error("Window not found");
      snapshot();
      setWindows((prev) => {
        const filtered = prev.filter((w) => w.id !== windowId);
        const optimistic: ActivityWindow = {
          ...original,
          id: -windowId,
          activity_type: newSlug,
          activity_label: newSlug,
          confidence: 1.0,
          confirmed_by_user: false,
          correction_of_window_id: windowId,
        };
        return [...filtered, optimistic].sort(
          (a, b) =>
            new Date(a.started_at).getTime() - new Date(b.started_at).getTime()
        );
      });
      try {
        const updated = await patchWindow(windowId, { activity_type_slug: newSlug });
        setWindows((prev) => {
          const without = prev.filter((w) => w.id !== windowId && w.id !== -windowId);
          return [...without, updated].sort(
            (a, b) =>
              new Date(a.started_at).getTime() - new Date(b.started_at).getTime()
          );
        });
        clearSnapshot();
        const day = original.started_at.slice(0, 10);
        await refetchDay(day);
        return updated;
      } catch (e) {
        fail(e);
        throw e;
      }
    },
    [windows, snapshot, setWindows, clearSnapshot, fail, refetchDay]
  );

  const addManualWindow = useCallback(
    async (data: ManualWindowInput): Promise<ActivityWindow> => {
      snapshot();
      const optimistic: ActivityWindow = {
        id: -Date.now(),
        started_at: data.started_at,
        ended_at: data.ended_at,
        activity_type: data.activity_type_slug,
        activity_label: data.activity_type_slug,
        color: "#6366f1",
        confidence: 1.0,
        sources: ["manual"],
        segment_ids: [],
        segment_count: 1,
        confirmed_by_user: false,
        dismissed_by_user: false,
        correction_of_window_id: null,
      };
      setWindows((prev) => [...prev, optimistic]);
      try {
        const created = await createManualWindow(data);
        setWindows((prev) =>
          [...prev.filter((w) => w.id !== optimistic.id), created].sort(
            (a, b) =>
              new Date(a.started_at).getTime() - new Date(b.started_at).getTime()
          )
        );
        clearSnapshot();
        await refetchDay(data.started_at.slice(0, 10));
        return created;
      } catch (e) {
        fail(e);
        throw e;
      }
    },
    [snapshot, setWindows, clearSnapshot, fail, refetchDay]
  );

  const deleteManualWindowById = useCallback(
    async (windowId: number): Promise<void> => {
      snapshot();
      setWindows((prev) => prev.filter((w) => w.id !== windowId));
      try {
        await deleteManualWindow(windowId);
        clearSnapshot();
        if (range) await refetchRange(range.from, range.to);
      } catch (e) {
        fail(e);
        throw e;
      }
    },
    [snapshot, setWindows, clearSnapshot, fail, range, refetchRange]
  );

  return {
    confirmWindow,
    dismissWindow,
    correctWindowType,
    addManualWindow,
    deleteManualWindow: deleteManualWindowById,
  };
}
