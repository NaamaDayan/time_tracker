"use client";

import {
  DndContext,
  KeyboardSensor,
  PointerSensor,
  closestCenter,
  useSensor,
  useSensors,
  type DragEndEvent,
} from "@dnd-kit/core";
import {
  SortableContext,
  arrayMove,
  sortableKeyboardCoordinates,
  useSortable,
  verticalListSortingStrategy,
} from "@dnd-kit/sortable";
import { CSS } from "@dnd-kit/utilities";
import type { ActivityPriorityItem, ActivityType } from "@/lib/types";
import { resolveActivityDisplay } from "@/lib/activityRegistry";
import styles from "./PriorityRankList.module.css";

interface PriorityRankListProps {
  localOrder: string[];
  enabledBySlug: Record<string, boolean>;
  itemsBySlug: Map<string, ActivityPriorityItem>;
  activityTypes: ActivityType[];
  onReorder: (order: string[]) => void;
}

function SortableRow({
  slug,
  rank,
  item,
  activityTypes,
  disabled,
}: {
  slug: string;
  rank: number;
  item: ActivityPriorityItem | undefined;
  activityTypes: ActivityType[];
  disabled: boolean;
}) {
  const { attributes, listeners, setNodeRef, transform, transition, isDragging } =
    useSortable({ id: slug, disabled });

  const display = item
    ? {
        label: item.display_name,
        color: item.color,
        emoji: item.emoji,
      }
    : resolveActivityDisplay(slug, activityTypes);

  const style = {
    transform: CSS.Transform.toString(transform),
    transition,
    borderLeftColor: display.color,
  };

  return (
    <li
      ref={setNodeRef}
      style={style}
      className={`${styles.row} ${disabled ? styles.rowDisabled : ""} ${isDragging ? styles.dragging : ""}`}
    >
      <button
        type="button"
        className={styles.handle}
        aria-label={`Drag to reorder ${display.label}`}
        disabled={disabled}
        {...(disabled ? {} : { ...attributes, ...listeners })}
      >
        ⠿
      </button>
      <span className={styles.rank}>{rank}</span>
      <span className={styles.emoji} aria-hidden>
        {display.emoji}
      </span>
      <span className={styles.label}>{display.label}</span>
      {disabled && <span className={styles.disabledNote}>(disabled in rules)</span>}
    </li>
  );
}

function StaticRow({
  slug,
  rank,
  item,
  activityTypes,
}: {
  slug: string;
  rank: number;
  item: ActivityPriorityItem | undefined;
  activityTypes: ActivityType[];
}) {
  const display = item
    ? {
        label: item.display_name,
        color: item.color,
        emoji: item.emoji,
      }
    : resolveActivityDisplay(slug, activityTypes);

  return (
    <li className={`${styles.row} ${styles.rowDisabled}`} style={{ borderLeftColor: display.color }}>
      <span className={styles.handle} aria-hidden>
        ⠿
      </span>
      <span className={styles.rank}>{rank}</span>
      <span className={styles.emoji} aria-hidden>
        {display.emoji}
      </span>
      <span className={styles.label}>{display.label}</span>
      <span className={styles.disabledNote}>(disabled in rules)</span>
    </li>
  );
}

export function PriorityRankList({
  localOrder,
  enabledBySlug,
  itemsBySlug,
  activityTypes,
  onReorder,
}: PriorityRankListProps) {
  const enabledSlugs = localOrder.filter((slug) => enabledBySlug[slug] !== false);
  const disabledSlugs = localOrder.filter((slug) => enabledBySlug[slug] === false);

  function handleDragEnd(event: DragEndEvent) {
    const { active, over } = event;
    if (!over || active.id === over.id) return;
    const oldIndex = enabledSlugs.indexOf(String(active.id));
    const newIndex = enabledSlugs.indexOf(String(over.id));
    if (oldIndex < 0 || newIndex < 0) return;
    const nextEnabled = arrayMove(enabledSlugs, oldIndex, newIndex);
    onReorder([...nextEnabled, ...disabledSlugs]);
  }

  const sensors = useSensors(
    useSensor(PointerSensor, { activationConstraint: { distance: 6 } }),
    useSensor(KeyboardSensor, { coordinateGetter: sortableKeyboardCoordinates })
  );

  return (
    <div>
      <DndContext
        sensors={sensors}
        collisionDetection={closestCenter}
        onDragEnd={handleDragEnd}
      >
        <SortableContext items={enabledSlugs} strategy={verticalListSortingStrategy}>
          <ul className={styles.list}>
            {enabledSlugs.map((slug, index) => (
              <SortableRow
                key={slug}
                slug={slug}
                rank={index + 1}
                item={itemsBySlug.get(slug)}
                activityTypes={activityTypes}
                disabled={false}
              />
            ))}
          </ul>
        </SortableContext>
      </DndContext>
      {disabledSlugs.length > 0 && (
        <ul className={styles.list} style={{ marginTop: 8 }}>
          {disabledSlugs.map((slug, index) => (
            <StaticRow
              key={slug}
              slug={slug}
              rank={enabledSlugs.length + index + 1}
              item={itemsBySlug.get(slug)}
              activityTypes={activityTypes}
            />
          ))}
        </ul>
      )}
    </div>
  );
}
