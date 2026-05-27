"use client";

import { useState, useEffect } from "react";
import { createActivityType } from "@/lib/api";
import type { ActivityType, GpsZone, GpsZoneCreateInput, GpsZoneUpdateInput, ZoneCategory } from "@/lib/types";
import styles from "./ZonePopover.module.css";

const CATEGORIES: ZoneCategory[] = [
  "home", "work", "gym", "family", "social", "transit", "other",
];

const DEFAULT_COLORS = [
  "#3b82f6", "#22c55e", "#ef4444", "#f59e0b", "#8b5cf6",
  "#ec4899", "#14b8a6", "#f97316", "#6366f1", "#84cc16",
];

interface ZonePopoverProps {
  lat: number;
  lon: number;
  zone?: GpsZone | null;
  activityTypes: ActivityType[];
  onSave: (body: GpsZoneCreateInput | GpsZoneUpdateInput) => Promise<void>;
  onDelete?: () => Promise<void>;
  onClose: () => void;
  onActivityTypeCreated?: (atype: ActivityType) => void;
}

const CATEGORY_DEFAULTS: Record<ZoneCategory, string | null> = {
  home: null,
  work: "work",
  gym: "sport",
  family: "fun",
  social: "fun",
  transit: "transport",
  other: null,
};

export function ZonePopover({
  lat,
  lon,
  zone,
  activityTypes,
  onSave,
  onDelete,
  onClose,
  onActivityTypeCreated,
}: ZonePopoverProps) {
  const [name, setName] = useState(zone?.name ?? "");
  const [category, setCategory] = useState<ZoneCategory>(zone?.category ?? "other");
  const [radius, setRadius] = useState(zone?.radius_meters ?? 150);
  const [activitySlug, setActivitySlug] = useState<string | null>(
    zone?.activity_type_slug ?? CATEGORY_DEFAULTS["other"]
  );
  const [saving, setSaving] = useState(false);
  const [creatingType, setCreatingType] = useState(false);
  const [newTypeSlug, setNewTypeSlug] = useState("");
  const [newTypeLabel, setNewTypeLabel] = useState("");

  useEffect(() => {
    const defaultSlug = CATEGORY_DEFAULTS[category];
    if (!zone || zone.category !== category) {
      setActivitySlug(defaultSlug);
    }
  }, [category, zone]);

  const handleCreateActivityType = async () => {
    if (!newTypeSlug.trim()) return;
    const slug = newTypeSlug.trim().toLowerCase().replace(/\s+/g, "_");
    const label = newTypeLabel.trim() || slug.charAt(0).toUpperCase() + slug.slice(1).replace(/_/g, " ");
    const color = DEFAULT_COLORS[Math.floor(Math.random() * DEFAULT_COLORS.length)];

    try {
      const atype = await createActivityType({ slug, label, color });
      setActivitySlug(atype.slug);
      setCreatingType(false);
      setNewTypeSlug("");
      setNewTypeLabel("");
      onActivityTypeCreated?.(atype);
    } catch {
      // slug may already exist on the server; just use it
      setActivitySlug(slug);
      setCreatingType(false);
    }
  };

  const handleSave = async () => {
    if (!name.trim()) return;
    setSaving(true);
    try {
      if (zone) {
        const body: GpsZoneUpdateInput = {
          name: name.trim(),
          category,
          radius_meters: radius,
          activity_type_slug: activitySlug,
        };
        await onSave(body);
      } else {
        const body: GpsZoneCreateInput = {
          name: name.trim(),
          category,
          lat,
          lon,
          radius_meters: radius,
          activity_type_slug: activitySlug,
        };
        await onSave(body);
      }
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className={styles.popover}>
      <div className={styles.header}>
        <h3>{zone ? "Edit Zone" : "Add Zone"}</h3>
        <button className={styles.closeBtn} onClick={onClose} aria-label="Close">
          &times;
        </button>
      </div>

      <label className={styles.field}>
        <span>Name</span>
        <input
          type="text"
          value={name}
          onChange={(e) => setName(e.target.value)}
          placeholder="e.g. My Gym"
          autoFocus
        />
      </label>

      <label className={styles.field}>
        <span>Category</span>
        <select value={category} onChange={(e) => setCategory(e.target.value as ZoneCategory)}>
          {CATEGORIES.map((c) => (
            <option key={c} value={c}>
              {c.charAt(0).toUpperCase() + c.slice(1)}
            </option>
          ))}
        </select>
      </label>

      <label className={styles.field}>
        <span>Radius: {radius}m</span>
        <input
          type="range"
          min={50}
          max={500}
          step={25}
          value={radius}
          onChange={(e) => setRadius(Number(e.target.value))}
        />
      </label>

      <div className={styles.field}>
        <span>Activity type</span>
        {!creatingType ? (
          <div className={styles.activityRow}>
            <select
              value={activitySlug ?? ""}
              onChange={(e) => {
                if (e.target.value === "__new__") {
                  setCreatingType(true);
                } else {
                  setActivitySlug(e.target.value || null);
                }
              }}
              className={styles.activitySelect}
            >
              <option value="">None (no segment)</option>
              {activityTypes.map((t) => (
                <option key={t.slug} value={t.slug}>
                  {t.label}
                </option>
              ))}
              <option value="__new__">+ New type...</option>
            </select>
          </div>
        ) : (
          <div className={styles.newTypeForm}>
            <input
              type="text"
              value={newTypeSlug}
              onChange={(e) => setNewTypeSlug(e.target.value)}
              placeholder="slug (e.g. yoga)"
              className={styles.newTypeInput}
            />
            <input
              type="text"
              value={newTypeLabel}
              onChange={(e) => setNewTypeLabel(e.target.value)}
              placeholder="Label (optional)"
              className={styles.newTypeInput}
            />
            <div className={styles.newTypeActions}>
              <button
                className={styles.newTypeBtn}
                onClick={handleCreateActivityType}
                disabled={!newTypeSlug.trim()}
              >
                Create
              </button>
              <button
                className={styles.newTypeCancelBtn}
                onClick={() => { setCreatingType(false); setNewTypeSlug(""); setNewTypeLabel(""); }}
              >
                Cancel
              </button>
            </div>
          </div>
        )}
      </div>

      <div className={styles.coords}>
        {lat.toFixed(5)}, {lon.toFixed(5)}
      </div>

      <div className={styles.actions}>
        {zone && onDelete && (
          <button className={styles.deleteBtn} onClick={onDelete}>
            Delete
          </button>
        )}
        <button className={styles.saveBtn} onClick={handleSave} disabled={saving || !name.trim()}>
          {saving ? "Saving..." : "Save"}
        </button>
      </div>
    </div>
  );
}
