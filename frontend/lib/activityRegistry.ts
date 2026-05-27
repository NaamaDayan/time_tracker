import type { ActivityType } from "@/lib/types";

/**
 * UI-only metadata keyed by activity slug. Labels and colors always come from the API
 * (`GET /activity-types`) via resolveActivityDisplay().
 */
export const ACTIVITY_UI_EXTRAS: Record<
  string,
  { emoji: string; recipe?: string }
> = {
  sleep: {
    emoji: "😴",
    recipe:
      "Samsung Watch confirms sleep, OR screen-off for {min_duration} min overnight",
  },
  work: {
    emoji: "💼",
    recipe:
      "Mac is in use, OR a calendar meeting has ≥2 attendees, OR GPS = work zone — during work hours on work days",
  },
  fun: {
    emoji: "🎉",
    recipe:
      "GPS = social/restaurant/bar zone, computer not in use, for at least {min_duration} min",
  },
  family: {
    emoji: "👨‍👩‍👧",
    recipe: "GPS = family zone for at least {min_duration} min",
  },
  sport: {
    emoji: "🏋️",
    recipe: "GPS = gym zone for at least {min_duration} min",
  },
  meal_prep: {
    emoji: "🍳",
    recipe: "Kitchen / meal-related activity for at least {min_duration} min",
  },
  bathroom: {
    emoji: "🚿",
    recipe: "Short bathroom visit ({min_duration}–{max_duration} min typical)",
  },
  bedroom: {
    emoji: "🛏️",
    recipe: "Time in bedroom zone for at least {min_duration} min",
  },
  watching_tv: {
    emoji: "📺",
    recipe: "TV or streaming on a large screen for at least {min_duration} min",
  },
  consuming: {
    emoji: "📱",
    recipe: "YouTube, social feeds, or similar for at least {min_duration} min",
  },
  music: {
    emoji: "🎵",
    recipe: "Music playback for at least {min_duration} min",
  },
  podcasts: {
    emoji: "🎧",
    recipe: "Podcast listening for at least {min_duration} min",
  },
  communication: {
    emoji: "💬",
    recipe:
      "Calls, chat, or meetings (phone or desktop) for at least {min_duration} min",
  },
  transport: {
    emoji: "🚌",
    recipe: "Moving between places (GPS / transit) for at least {min_duration} min",
  },
};

const DEFAULT_COLOR = "#6366f1";

function formatSlugAsLabel(slug: string): string {
  return slug
    .split("_")
    .map((w) => w.charAt(0).toUpperCase() + w.slice(1))
    .join(" ");
}

export interface ActivityDisplay {
  slug: string;
  label: string;
  color: string;
  emoji: string;
}

/** Single resolver: API label/color + registry emoji. */
export function resolveActivityDisplay(
  slug: string,
  activityTypes: ActivityType[]
): ActivityDisplay {
  const fromApi = activityTypes.find((t) => t.slug === slug);
  const extras = ACTIVITY_UI_EXTRAS[slug];
  return {
    slug,
    label: fromApi?.label ?? formatSlugAsLabel(slug),
    color: fromApi?.color ?? DEFAULT_COLOR,
    emoji: extras?.emoji ?? "📌",
  };
}

export function formatActivityRecipe(
  slug: string,
  minDuration: number,
  activityTypes: ActivityType[],
  maxDuration?: number
): string {
  const { label } = resolveActivityDisplay(slug, activityTypes);
  const template =
    ACTIVITY_UI_EXTRAS[slug]?.recipe ??
    `${label} for at least {min_duration} min`;
  let text = template.replace(/\{min_duration\}/g, String(minDuration));
  if (maxDuration !== undefined) {
    text = text.replace(/\{max_duration\}/g, String(maxDuration));
  }
  return text;
}

/** Build a slug → display map for fast lookups in lists. */
export function buildActivityDisplayMap(
  activityTypes: ActivityType[]
): Map<string, ActivityDisplay> {
  const slugs = new Set([
    ...activityTypes.map((t) => t.slug),
    ...Object.keys(ACTIVITY_UI_EXTRAS),
  ]);
  const map = new Map<string, ActivityDisplay>();
  for (const slug of slugs) {
    map.set(slug, resolveActivityDisplay(slug, activityTypes));
  }
  return map;
}
