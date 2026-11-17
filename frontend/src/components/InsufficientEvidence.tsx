import type { JourneyOption } from "../api/types";
import { ReasonBlock } from "./ReasonBlock";

interface Props {
  option: JourneyOption;
  /** Lets the card send the user to the Fastest option, which only needs the timetable. */
  onShowFastest?: () => void;
}

/**
 * Explicit "insufficient evidence" state.
 *
 * This is not an error and not "low crowding": scheduled journeys exist, but the
 * ticket evidence is too thin to rank them on crowding. Styled neutral and hatched.
 */
export function InsufficientEvidence({ option, onShowFastest }: Props) {
  return (
    <article className="card card--insufficient" data-testid="insufficient-evidence" aria-label={`${option.label}: insufficient evidence`}>
      <p className="state-tag state-tag--unknown">Insufficient evidence</p>
      <h3 className="card__title">{option.label}: not enough evidence to rank</h3>
      <p className="card__lead">
        Scheduled journeys exist for this search, but there are too few ticket samples to rank them on
        crowding. This means crowding is unknown here. It does not mean these buses are less crowded.
      </p>
      <ReasonBlock reason={option.reason} heading="Why there is no ranking" />
      {onShowFastest && (
        <button type="button" className="button button--secondary" onClick={onShowFastest}>
          Show the Fastest option instead
        </button>
      )}
      <p className="card__footnote">Fastest uses the timetable only, so it does not need ticket evidence.</p>
    </article>
  );
}
