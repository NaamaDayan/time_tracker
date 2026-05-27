"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { getRuleConfigs, updateRuleConfig } from "@/lib/api";
import type { ActivityRuleConfig, ActivityRuleConfigUpdateInput } from "@/lib/types";

const DEBOUNCE_MS = 800;

export function useRuleConfigs() {
  const [configs, setConfigs] = useState<ActivityRuleConfig[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [savingSlug, setSavingSlug] = useState<string | null>(null);
  const [savedSlug, setSavedSlug] = useState<string | null>(null);
  const timersRef = useRef<Record<string, ReturnType<typeof setTimeout>>>({});
  const savedTimersRef = useRef<Record<string, ReturnType<typeof setTimeout>>>({});

  const refresh = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const data = await getRuleConfigs();
      setConfigs(data);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to load rule configs");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    refresh();
    return () => {
      Object.values(timersRef.current).forEach(clearTimeout);
      Object.values(savedTimersRef.current).forEach(clearTimeout);
    };
  }, [refresh]);

  const update = useCallback(
    async (slug: string, patch: ActivityRuleConfigUpdateInput) => {
      setSavingSlug(slug);
      try {
        const updated = await updateRuleConfig(slug, patch);
        setConfigs((prev) =>
          prev
            .map((c) => (c.activity_type_slug === slug ? updated : c))
            .sort((a, b) => a.activity_type_slug.localeCompare(b.activity_type_slug))
        );
        setSavedSlug(slug);
        if (savedTimersRef.current[slug]) clearTimeout(savedTimersRef.current[slug]);
        savedTimersRef.current[slug] = setTimeout(() => {
          setSavedSlug((current) => (current === slug ? null : current));
        }, 2000);
      } finally {
        setSavingSlug((current) => (current === slug ? null : current));
      }
    },
    []
  );

  const pendingRef = useRef<Record<string, ActivityRuleConfigUpdateInput>>({});

  const debouncedUpdate = useCallback(
    (slug: string, patch: ActivityRuleConfigUpdateInput) => {
      const prevPending = pendingRef.current[slug] ?? {};
      pendingRef.current[slug] = {
        ...prevPending,
        ...patch,
        boost_signals: patch.boost_signals
          ? { ...prevPending.boost_signals, ...patch.boost_signals }
          : prevPending.boost_signals,
        custom_params: patch.custom_params
          ? { ...prevPending.custom_params, ...patch.custom_params }
          : prevPending.custom_params,
      };

      setConfigs((prev) =>
        prev.map((c) => {
          if (c.activity_type_slug !== slug) return c;
          const p = pendingRef.current[slug]!;
          return {
            ...c,
            ...p,
            boost_signals: p.boost_signals ?? c.boost_signals,
            custom_params: p.custom_params ?? c.custom_params,
          };
        })
      );

      if (timersRef.current[slug]) clearTimeout(timersRef.current[slug]);
      timersRef.current[slug] = setTimeout(() => {
        const merged = pendingRef.current[slug];
        delete pendingRef.current[slug];
        if (merged) void update(slug, merged);
      }, DEBOUNCE_MS);
    },
    [update]
  );

  return {
    configs,
    loading,
    error,
    refresh,
    update,
    debouncedUpdate,
    savingSlug,
    savedSlug,
  };
}
