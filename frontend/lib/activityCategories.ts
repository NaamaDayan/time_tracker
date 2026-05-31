/** UI grouping for activity type selects (no API category field). */

export type ActivityCategory =
  | "Work"
  | "Health"
  | "Home"
  | "Social"
  | "Media"
  | "Other";

const SLUG_TO_CATEGORY: Record<string, ActivityCategory> = {
  work: "Work",
  communication: "Work",
  sleep: "Health",
  sport: "Health",
  family: "Home",
  meal_prep: "Home",
  bathroom: "Home",
  bedroom: "Home",
  fun: "Social",
  transport: "Social",
  consuming: "Media",
  screen_time: "Media",
  watching_tv: "Media",
  music: "Media",
  podcasts: "Media",
  music_podcast: "Media",
  read: "Media",
  phone_usage: "Media",
};

export function activityCategory(slug: string): ActivityCategory {
  return SLUG_TO_CATEGORY[slug] ?? "Other";
}

export const CATEGORY_ORDER: ActivityCategory[] = [
  "Work",
  "Health",
  "Home",
  "Social",
  "Media",
  "Other",
];

export function groupActivitySlugs(
  slugs: string[],
  excludeSlug?: string
): Map<ActivityCategory, string[]> {
  const map = new Map<ActivityCategory, string[]>();
  for (const cat of CATEGORY_ORDER) {
    map.set(cat, []);
  }
  for (const slug of slugs) {
    if (slug === excludeSlug) continue;
    const cat = activityCategory(slug);
    map.get(cat)!.push(slug);
  }
  for (const cat of CATEGORY_ORDER) {
    map.get(cat)!.sort();
  }
  return map;
}
