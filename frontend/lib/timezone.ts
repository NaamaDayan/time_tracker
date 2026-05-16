/**
 * FullCalendar does not convert UTC event times when `timeZone` is a named IANA zone.
 * Convert API timestamps (UTC) to floating local datetimes in the configured zone.
 */
export function utcIsoToCalendarLocal(iso: string, timeZone: string): string {
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return iso;

  return new Intl.DateTimeFormat("sv-SE", {
    timeZone,
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
    hourCycle: "h23",
  })
    .format(d)
    .replace(" ", "T");
}
