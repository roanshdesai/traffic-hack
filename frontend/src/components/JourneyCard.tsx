import type { Journey, JourneyOption } from "../api/types";
import { KIND_LABEL, formatClock, formatMinutes, plural } from "../lib/format";
import { CrowdingBadge } from "./CrowdingBadge";
import { EvidenceBadge } from "./EvidenceBadge";
import { LegTimeline } from "./LegTimeline";
import { ReasonBlock } from "./ReasonBlock";

interface Props {
  option: JourneyOption;
  journey: Journey;
}

function coverageText(journey: Journey): string {
  const { covered_min, in_vehicle_min } = journey.crowding;
  return `Evidence for ${Math.round(covered_min)} of ${Math.round(in_vehicle_min)} scheduled min on board`;
}

/** The selected option when a journey was found (`status: "ok"`). */
export function JourneyCard({ option, journey }: Props) {
  const { crowding } = journey;
  const transfersText = journey.transfers === 0 ? "Direct" : plural(journey.transfers, "change");

  return (
    <article className="card card--journey" data-testid="journey-card" aria-label={`${option.label} journey`}>
      <header className="journey-head">
        <p className="journey-head__kind">{option.label}</p>
        <p className="journey-head__times">
          <span className="journey-head__clock">{formatClock(journey.scheduled_departure)}</span>
          <span className="journey-head__arrow" aria-hidden="true">
            →
          </span>
          <span className="visually-hidden"> to </span>
          <span className="journey-head__clock">{formatClock(journey.scheduled_arrival)}</span>
        </p>
        <p className="journey-head__caption">Scheduled departure and arrival (timetable, not live)</p>
      </header>

      {option.same_journey_as && (
        <p className="same-as" data-testid="same-as">
          Same journey as {KIND_LABEL[option.same_journey_as]}.
        </p>
      )}

      <dl className="stats">
        <div className="stats__item">
          <dt>Scheduled travel time</dt>
          <dd>{formatMinutes(journey.scheduled_travel_min)}</dd>
        </div>
        <div className="stats__item">
          <dt>Wait before departure</dt>
          <dd>{formatMinutes(journey.initial_wait_min)}</dd>
        </div>
        <div className="stats__item">
          <dt>Changes</dt>
          <dd>{transfersText}</dd>
        </div>
      </dl>

      <ReasonBlock reason={option.reason} />

      <section className="crowding-summary" aria-label="Relative crowding for this journey">
        <h4 className="crowding-summary__heading">Relative crowding (from ticket samples)</h4>
        <div className="crowding-summary__badges">
          <CrowdingBadge level={crowding.level} />
          <EvidenceBadge quality={crowding.evidence_quality} />
        </div>
        <p className="crowding-summary__coverage">{coverageText(journey)}</p>
        {crowding.min_segment_ticket_count > 0 && (
          <p className="crowding-summary__coverage">
            Thinnest segment with evidence: {plural(crowding.min_segment_ticket_count, "ticket")}
          </p>
        )}
      </section>

      <LegTimeline legs={journey.legs} />
    </article>
  );
}
