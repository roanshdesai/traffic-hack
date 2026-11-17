import type { CrowdingLevel } from "../api/types";
import { LEVEL_LABEL } from "../lib/format";

const FILLED_BARS: Record<CrowdingLevel, number> = {
  lower: 1,
  typical: 2,
  higher: 3,
  insufficient_evidence: 0,
};

interface MeterProps {
  level: CrowdingLevel;
}

/**
 * Three-bar cue: 1, 2 or 3 filled bars for lower / typical / higher, and three
 * dashed outlines for "not enough evidence". The bar count carries the meaning,
 * so the cue never relies on colour alone. Decorative: always paired with text.
 */
export function CrowdingMeter({ level }: MeterProps) {
  const filled = FILLED_BARS[level];
  return (
    <span className={`meter meter--${level}`} aria-hidden="true">
      {[1, 2, 3].map((n) => (
        <span key={n} className={`meter__bar ${n <= filled ? "meter__bar--on" : ""}`} />
      ))}
    </span>
  );
}

interface Props {
  level: CrowdingLevel;
  /** "badge" has a border and background; "inline" is text + meter only. */
  variant?: "badge" | "inline";
}

/** Relative crowding label. Relative wording only: never seats, occupancy or a percentage. */
export function CrowdingBadge({ level, variant = "badge" }: Props) {
  return (
    <span className={`crowding crowding--${variant} crowding--${level}`} data-level={level}>
      <CrowdingMeter level={level} />
      <span className="crowding__label">{LEVEL_LABEL[level]}</span>
    </span>
  );
}
