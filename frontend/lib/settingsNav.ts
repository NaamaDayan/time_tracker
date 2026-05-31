/** Add new settings sections here — sidebar and home page read from this list. */
export const SETTINGS_NAV_ITEMS = [
  {
    href: "/settings/rules",
    label: "Activity rules",
    description:
      "Tune minimum duration, merge gaps, work hours, and detection toggles per activity type.",
  },
  {
    href: "/settings/zones",
    label: "GPS zones",
    description:
      "Map named places (home, office, gym) that drive location-based activity detection.",
  },
  {
    href: "/settings/priority",
    label: "Activity priority",
    description:
      "Drag to set which activity wins when two overlap in the pie chart view.",
  },
] as const;
