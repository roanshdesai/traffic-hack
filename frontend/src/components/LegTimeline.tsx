import { Fragment } from "react";
import type { BusLeg, Leg, Segment, TransferLeg } from "../api/types";
import { BASIS_LABEL, formatClock, formatDistance, formatMinutes, supportText } from "../lib/format";
import { CrowdingBadge } from "./CrowdingBadge";
import { EvidenceBadge } from "./EvidenceBadge";

function SegmentRow({ segment }: { segment: Segment }) {
  const { crowding } = segment;
  const { evidence } = crowding;
  return (
    <li className={`tl-segment tl-segment--${crowding.level}`} data-testid="segment" data-level={crowding.level}>
      <span className="tl-segment__rail" aria-hidden="true" />
      <div className="tl-segment__body">
        <div className="tl-segment__top">
          <CrowdingBadge level={crowding.level} variant="inline" />
          <span className="tl-segment__duration">{formatMinutes(segment.scheduled_min)}</span>
        </div>
        <p className="tl-segment__support">
          {supportText(evidence.ticket_count, evidence.service_days)} · {BASIS_LABEL[evidence.basis]}
          {crowding.level === "insufficient_evidence" && evidence.min_tickets_required > 0 && (
            <> · needs at least {evidence.min_tickets_required} tickets</>
          )}
        </p>
        <EvidenceBadge quality={evidence.quality} />
      </div>
    </li>
  );
}

function BusLegView({ leg }: { leg: BusLeg }) {
  return (
    <section className="leg leg--bus" aria-label={`Bus ${leg.route.short_name} towards ${leg.headsign}`}>
      <header className="leg__header">
        <span className="route-chip">{leg.route.short_name}</span>
        <div className="leg__heading">
          <h4 className="leg__title">towards {leg.headsign}</h4>
          <p className="leg__meta">
            {leg.route.long_name} · {formatMinutes(leg.scheduled_min)} scheduled · {leg.stops.length} stops
          </p>
        </div>
      </header>
      <ol className="timeline">
        {leg.stops.map((stop, i) => {
          const isFirst = i === 0;
          const isLast = i === leg.stops.length - 1;
          const clock = isFirst ? stop.scheduled_departure : stop.scheduled_arrival;
          const segment = leg.segments[i];
          return (
            <Fragment key={`${stop.stop_id}-${stop.sequence}`}>
              <li className={`tl-stop ${isFirst || isLast ? "tl-stop--end" : ""}`} data-testid="stop">
                <span className="tl-stop__time">{formatClock(clock)}</span>
                <span className="tl-stop__dot" aria-hidden="true" />
                <span className="tl-stop__name">
                  {stop.name}
                  {isFirst && <span className="tl-stop__role"> · board</span>}
                  {isLast && <span className="tl-stop__role"> · get off</span>}
                </span>
              </li>
              {!isLast && segment && <SegmentRow segment={segment} />}
            </Fragment>
          );
        })}
      </ol>
    </section>
  );
}

function TransferLegView({ leg }: { leg: TransferLeg }) {
  const samePlace = leg.from_stop.name === leg.to_stop.name;
  return (
    <section className="leg leg--transfer" aria-label="Change buses" data-testid="transfer">
      <span className="leg__transfer-icon" aria-hidden="true">
        ⇄
      </span>
      <p className="leg__transfer-text">
        Change at <strong>{leg.from_stop.name}</strong>
        {!samePlace && (
          <>
            {" "}
            (next bus from <strong>{leg.to_stop.name}</strong>)
          </>
        )}
        , scheduled gap {formatMinutes(leg.scheduled_min)}, {formatDistance(leg.walk_m)} walk
      </p>
    </section>
  );
}

interface Props {
  legs: Leg[];
}

/** Ordered legs of a journey: stop-by-stop timelines with segment-level relative crowding. */
export function LegTimeline({ legs }: Props) {
  return (
    <div className="legs">
      <p className="legs__note">
        All times are scheduled. Crowding between stops is relative to other segments in this dataset.
      </p>
      {legs.map((leg, i) =>
        leg.type === "bus" ? <BusLegView key={i} leg={leg} /> : <TransferLegView key={i} leg={leg} />,
      )}
    </div>
  );
}
