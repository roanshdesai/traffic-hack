import type { Provenance } from "../api/types";

interface Props {
  provenance: Provenance | null | undefined;
}

/**
 * Persistent notice shown whenever any input dataset is synthetic.
 * Contract rule: must be visible on every screen that shows results.
 */
export function SimulatedBanner({ provenance }: Props) {
  if (!provenance?.simulated) return null;
  return (
    <div className="sim-banner" role="note" aria-label="Simulated data notice">
      <span className="sim-banner__tag">Simulated data</span>
      <span className="sim-banner__text">
        Routes, stops, timetables and ticket samples here are synthetic demo fixtures. Nothing shown
        reflects real Delhi bus services or real crowding.
      </span>
    </div>
  );
}
