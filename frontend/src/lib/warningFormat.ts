import type { Quality, Site, SourceKind, Status, WindowAssessment } from "../api/warningTypes";

/**
 * Wording is fixed by the contract (docs/API.md). Never say live, real-time,
 * verified, seats or "% full" about a reading.
 */
export const STATUS_LABEL: Record<Status, string> = {
  normal: "Usual for this time",
  elevated: "Busier than usual",
  overcrowding_alert: "Overcrowding alert",
  insufficient_evidence: "Not enough history",
  no_data: "No data",
};

/** Text icon paired with every status, so status never relies on colour alone. */
export const STATUS_ICON: Record<Status, string> = {
  normal: "●",
  elevated: "▲",
  overcrowding_alert: "‼",
  insufficient_evidence: "?",
  no_data: "–",
};

export const SOURCE_LABEL: Record<SourceKind, string> = {
  camera_count: "Camera count (estimate)",
  ticket_sample: "E-ticket sample",
  manual_count: "Manual count",
};

export const QUALITY_TEXT: Record<Quality, string> = {
  high: "Evidence: high",
  medium: "Evidence: medium",
  low: "Evidence: low",
  insufficient: "Evidence: insufficient",
};

/** Order for summary chips and sorting. */
export const STATUS_ORDER: Status[] = ["overcrowding_alert", "elevated", "normal", "insufficient_evidence", "no_data"];

const STAMP = /^(\d{4})-(\d{2})-(\d{2})T(\d{2}):(\d{2})/;

/**
 * Replay times are wall-clock strings without an offset. Arithmetic is done in
 * UTC on purpose so the viewer's own time zone can never shift a time.
 */
export function parseStamp(stamp: string): number | null {
  const m = STAMP.exec(stamp);
  if (!m) return null;
  return Date.UTC(Number(m[1]), Number(m[2]) - 1, Number(m[3]), Number(m[4]), Number(m[5]));
}

export function formatStamp(ms: number): string {
  const d = new Date(ms);
  const pad = (n: number) => String(n).padStart(2, "0");
  return `${d.getUTCFullYear()}-${pad(d.getUTCMonth() + 1)}-${pad(d.getUTCDate())}T${pad(d.getUTCHours())}:${pad(
    d.getUTCMinutes(),
  )}`;
}

export function addMinutes(stamp: string, minutes: number): string {
  const ms = parseStamp(stamp);
  return ms === null ? stamp : formatStamp(ms + minutes * 60_000);
}

/** Round down to a multiple of `step` minutes. */
export function snapStamp(stamp: string, step = 15): string {
  const ms = parseStamp(stamp);
  if (ms === null) return stamp;
  const stepMs = step * 60_000;
  return formatStamp(Math.floor(ms / stepMs) * stepMs);
}

/** "2026-11-18T17:45" -> "17:45". */
export function clockOf(stamp: string): string {
  const m = /T(\d{2}:\d{2})/.exec(stamp);
  return m ? m[1] : stamp;
}

/** "2026-11-18T17:45" -> "2026-11-18". */
export function dateOf(stamp: string): string {
  return stamp.slice(0, 10);
}

/** Minutes after midnight of a stamp's clock time. */
export function minuteOfDay(stamp: string): number {
  const m = /T(\d{2}):(\d{2})/.exec(stamp);
  return m ? Number(m[1]) * 60 + Number(m[2]) : 0;
}

/** Earliest and latest replay times allowed by a replay period. */
export function replayBounds(period: { start: string; end: string }): { min: string; max: string } {
  return { min: `${period.start}T00:00`, max: `${period.end}T23:45` };
}

export function clampStamp(stamp: string, bounds: { min: string; max: string }): string {
  if (stamp < bounds.min) return bounds.min;
  if (stamp > bounds.max) return bounds.max;
  return stamp;
}

export function formatNumber(value: number): string {
  return Number.isInteger(value) ? String(value) : String(Math.round(value));
}

/** 1.92 -> "1.9× usual". */
export function ratioText(ratio: number): string {
  return `${ratio.toFixed(1)}× usual`;
}

/**
 * One-line reading for a window, e.g. "182 people counted vs usually 95".
 * Uses only numbers present in the API response.
 */
export function readingText(site: Site, current: WindowAssessment): string {
  if (current.observed === null) return "No usable reading for this window";
  const observed = `${formatNumber(current.observed)} ${site.unit}`;
  if (!current.baseline) return `${observed} (no usual level for this time yet)`;
  return `${observed} vs usually ${formatNumber(current.baseline.median)}`;
}

/** "around 18:15 (in 30 min)". */
export function warningWhen(expectedAt: string, leadMin: number): string {
  return `around ${clockOf(expectedAt)} (in ${leadMin} min)`;
}

export function humanizeKind(kind: string): string {
  const text = kind.replace(/_/g, " ").trim();
  return text.charAt(0).toUpperCase() + text.slice(1);
}

/** Metric values from the evaluation endpoint, shown without inventing precision. */
export function metricText(value: unknown): string {
  if (value === null || value === undefined) return "n/a";
  if (typeof value === "number") return Number.isInteger(value) ? String(value) : value.toFixed(3).replace(/0+$/, "").replace(/\.$/, "");
  if (typeof value === "boolean") return value ? "yes" : "no";
  if (typeof value === "string") return value;
  if (Array.isArray(value)) return value.map(metricText).join(", ");
  return JSON.stringify(value);
}
