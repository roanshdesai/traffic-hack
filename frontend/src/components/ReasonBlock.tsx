import type { Reason } from "../api/types";

interface Props {
  reason: Reason;
  heading?: string;
}

/** Why an option got its ranking (or why it could not be ranked). */
export function ReasonBlock({ reason, heading = "Why this ranking" }: Props) {
  return (
    <section className="reason" aria-label={heading}>
      <h4 className="reason__heading">{heading}</h4>
      <p className="reason__summary">{reason.summary}</p>
      {reason.details.length > 0 && (
        <ul className="reason__details">
          {reason.details.map((detail, i) => (
            <li key={i}>{detail}</li>
          ))}
        </ul>
      )}
    </section>
  );
}
