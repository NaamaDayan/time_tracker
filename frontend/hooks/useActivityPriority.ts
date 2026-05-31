"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { getActivityPriority, getRuleConfigs, putActivityPriority } from "@/lib/api";
import { DEFAULT_PRIORITY_SLUGS } from "@/lib/activityPriorityDefaults";
import type { ActivityPriorityItem } from "@/lib/types";

function orderKey(slugs: string[]): string {
  return slugs.join("\0");
}

export function useActivityPriority() {
  const [items, setItems] = useState<ActivityPriorityItem[]>([]);
  const [localOrder, setLocalOrder] = useState<string[]>([]);
  const [savedOrder, setSavedOrder] = useState<string[]>([]);
  const [enabledBySlug, setEnabledBySlug] = useState<Record<string, boolean>>({});
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const refresh = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const [priority, ruleConfigs] = await Promise.all([
        getActivityPriority(),
        getRuleConfigs(),
      ]);
      const order = priority.map((p) => p.slug);
      setItems(priority);
      setLocalOrder(order);
      setSavedOrder(order);
      const enabled: Record<string, boolean> = {};
      for (const cfg of ruleConfigs) {
        enabled[cfg.activity_type_slug] = cfg.enabled;
      }
      setEnabledBySlug(enabled);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to load priority");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    refresh();
  }, [refresh]);

  const isDirty = useMemo(
    () => orderKey(localOrder) !== orderKey(savedOrder),
    [localOrder, savedOrder]
  );

  const getPriority = useCallback(async () => {
    await refresh();
    return items;
  }, [refresh, items]);

  const savePriority = useCallback(
    async (orderedSlugs: string[]) => {
      setSaving(true);
      setError(null);
      const body = orderedSlugs.map((slug, index) => ({
        slug,
        rank: index + 1,
      }));
      try {
        const updated = await putActivityPriority(body);
        const order = updated.map((p) => p.slug);
        setItems(updated);
        setLocalOrder(order);
        setSavedOrder(order);
        return true;
      } catch (e) {
        setLocalOrder(savedOrder);
        setError(e instanceof Error ? e.message : "Save failed");
        return false;
      } finally {
        setSaving(false);
      }
    },
    [savedOrder]
  );

  const resetToDefaults = useCallback((): string[] => {
    return [...DEFAULT_PRIORITY_SLUGS];
  }, []);

  const reorder = useCallback((nextOrder: string[]) => {
    setLocalOrder(nextOrder);
  }, []);

  const itemsBySlug = useMemo(() => {
    const map = new Map<string, ActivityPriorityItem>();
    for (const item of items) {
      map.set(item.slug, item);
    }
    return map;
  }, [items]);

  return {
    items,
    itemsBySlug,
    localOrder,
    savedOrder,
    enabledBySlug,
    loading,
    saving,
    error,
    isDirty,
    getPriority,
    savePriority,
    resetToDefaults,
    reorder,
    refresh,
  };
}
