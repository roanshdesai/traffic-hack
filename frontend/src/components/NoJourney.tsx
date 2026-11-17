import type { Reason } from "../api/types";

interface Props {
  title?: string;
  message: string;
  reason?: Reason;
}

/** Empty state: no scheduled journey in the search window. */
export function NoJourney({ title = "No scheduled journey found", message, reason }: Props) {
  return (
    <article className="card card--empty" data-testid="no-journey">
      <p className="state-tag state-tag--empty">No journey</p>
      <h3 className="card__title">{title}</h3>
      <p className="card__lead">{message}</p>
      {reason && reason.summary !== message && <p className="card__lead">{reason.summary}</p>}
      {reason && reason.details.length > 0 && (
        <ul className="reason__details">
          {reason.details.map((detail, i) => (
            <li key={i}>{detail}</li>
          ))}
        </ul>
      )}
      <p className="card__footnote">Try a different time or date, or another pair of stops.</p>
    </article>
  );
}
