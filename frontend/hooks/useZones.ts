"use client";

import { useCallback, useEffect, useState } from "react";
import {
  createZone,
  deleteZone,
  getZones,
  updateZone,
} from "@/lib/api";
import type { GpsZone, GpsZoneCreateInput, GpsZoneUpdateInput } from "@/lib/types";

export function useZones() {
  const [zones, setZones] = useState<GpsZone[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const refresh = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const data = await getZones();
      setZones(data);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to load zones");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    refresh();
  }, [refresh]);

  const addZone = useCallback(
    async (body: GpsZoneCreateInput) => {
      const zone = await createZone(body);
      setZones((prev) => [...prev, zone].sort((a, b) => a.name.localeCompare(b.name)));
      return zone;
    },
    []
  );

  const editZone = useCallback(
    async (id: string, body: GpsZoneUpdateInput) => {
      const updated = await updateZone(id, body);
      setZones((prev) =>
        prev.map((z) => (z.id === id ? updated : z)).sort((a, b) => a.name.localeCompare(b.name))
      );
      return updated;
    },
    []
  );

  const removeZone = useCallback(
    async (id: string) => {
      await deleteZone(id);
      setZones((prev) => prev.filter((z) => z.id !== id));
    },
    []
  );

  return { zones, loading, error, refresh, addZone, editZone, removeZone };
}
