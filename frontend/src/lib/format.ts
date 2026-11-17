import type { CrowdingLevel, EvidenceBasis, EvidenceQuality, OptionKind } from "../api/types";

/**
 * "2026-11-16T08:12:00+05:30" -> "08:12".
 *
 * The API sends local (Asia/Kolkata) times with an explicit offset. We slice the
 * string instead of using `Date`, so the result never depends on the viewer's
 * own time zone.
 */
export function formatClock(iso: string): string {
  const match = /T(\d{2}:\d{2})/.exec(iso);
  if (match) return match[1];
  const bare = /^(\d{2}:\d{2})/.exec(iso);
  return bare ? bare[1] : iso;
}

/** "2026-11-16T08:12:00+05:30" -> "2026-11-16". */
export function isoDatePart(iso: string): string {
  return iso.slice(0, 10);
}

/** 36 -> "36 min", 65 -> "1 h 05 min". Rounds to whole minutes. */
export function formatMinutes(minutes: number): string {
  const total = Math.max(0, Math.round(minutes));
  if (total < 60) return `${total} min`;
  const h = Math.floor(total / 60);
  const m = total % 60;
  return m === 0 ? `${h} h` : `${h} h ${String(m).padStart(2, "0")} min`;
}

export function formatDistance(metres: number): string {
  const rounded = metres < 100 ? Math.round(metres / 10) * 10 : Math.round(metres / 50) * 50;
  return `~${rounded} m`;
}

export function plural(count: number, singular: string, pluralForm = `${singular}s`): string {
  return `${count} ${count === 1 ? singular : pluralForm}`;
}

/** Wording is fixed by the contract. Never say seats, available, % full or live. */
export const LEVEL_LABEL: Record<CrowdingLevel, string> = {
  lower: "Relatively less crowded",
  typical: "About typical",
  higher: "Relatively more crowded",
  insufficient_evidence: "Not enough evidence",
};

export const QUALITY_LABEL: Record<EvidenceQuality, string> = {
  high: "Evidence: high",
  medium: "Evidence: medium",
  low: "Evidence: low",
  insufficient: "Evidence: insufficient",
};

export const BASIS_LABEL: Record<EvidenceBasis, string> = {
  segment_period_daytype: "this segment, this period and day type",
  segment_period: "pooled across day types",
  segment_all_day: "pooled across the whole day",
  none: "no usable samples",
};

export const KIND_LABEL: Record<OptionKind, string> = {
  fastest: "Fastest",
  balanced: "Balanced",
  less_crowded: "Less crowded",
};

/** "12 tickets over 5 days". */
export function supportText(ticketCount: number, serviceDays: number): string {
  return `${plural(ticketCount, "ticket")} over ${plural(serviceDays, "day")}`;
}

/** Current date and time in Asia/Kolkata, for form defaults. */
export function nowInDelhi(now: Date = new Date()): { date: string; time: string } {
  const parts = new Intl.DateTimeFormat("en-GB", {
    timeZone: "Asia/Kolkata",
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
    hourCycle: "h23",
  }).formatToParts(now);
  const get = (type: string) => parts.find((p) => p.type === type)?.value ?? "00";
  return {
    date: `${get("year")}-${get("month")}-${get("day")}`,
    time: `${get("hour")}:${get("minute")}`,
  };
}

/** snake_case -> "Snake case", for showing status codes from the data-quality report. */
export function humanize(code: string): string {
  const text = code.replace(/_/g, " ").trim();
  return text.charAt(0).toUpperCase() + text.slice(1);
}
