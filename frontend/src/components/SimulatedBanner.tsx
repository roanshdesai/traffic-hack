interface Props {
  /** Any provenance object with a `simulated` flag (planner or warning dataset). */
  provenance: { simulated: boolean } | null | undefined;
  /** Notice text. Defaults to the planner dataset wording. */
  text?: string;
}

export const PLANNER_SIMULATED_TEXT =
  "Routes, stops, timetables and ticket samples here are synthetic demo fixtures. Nothing shown reflects real Delhi bus services or real crowding.";

export const WARNING_SIMULATED_TEXT =
  "Simulated data: the sites, counts and events are synthetic test fixtures. Nothing here describes real places or real crowds.";

/**
 * Persistent notice shown whenever the dataset on screen is synthetic.
 * Contract rule: must be visible on every screen that shows results.
 */
export function SimulatedBanner({ provenance, text = PLANNER_SIMULATED_TEXT }: Props) {
  if (!provenance?.simulated) return null;
  return (
    <div className="sim-banner" role="note" aria-label="Simulated data notice">
      <span className="sim-banner__tag">Simulated data</span>
      <span className="sim-banner__text">{text}</span>
    </div>
  );
}
