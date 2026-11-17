import { useId } from "react";
import { addMinutes, clampStamp, clockOf, dateOf, snapStamp } from "../../lib/warningFormat";

interface Props {
  /** Current replay time, YYYY-MM-DDTHH:MM. */
  value: string;
  bounds: { min: string; max: string };
  stepMinutes?: number;
  busy?: boolean;
  onChange: (stamp: string) => void;
}

/**
 * Picks the moment to replay. Only data up to this time is used for the status and the
 * forecast, so stepping forward shows what the system would have said at each moment.
 */
export function ReplayControl({ value, bounds, stepMinutes = 15, busy = false, onChange }: Props) {
  const hintId = useId();
  const commit = (stamp: string) => onChange(clampStamp(snapStamp(stamp, stepMinutes), bounds));
  const atMin = value <= bounds.min;
  const atMax = value >= bounds.max;

  return (
    <section className="card replay" aria-labelledby={`${hintId}-title`} aria-busy={busy}>
      <h2 id={`${hintId}-title`} className="replay__title">
        Replay time
      </h2>
      <div className="replay__fields">
        <label className="field">
          <span className="field__label">Date</span>
          <input
            className="field__input"
            type="date"
            value={dateOf(value)}
            min={dateOf(bounds.min)}
            max={dateOf(bounds.max)}
            aria-describedby={hintId}
            onChange={(e) => {
              if (e.target.value) commit(`${e.target.value}T${clockOf(value)}`);
            }}
          />
        </label>
        <label className="field">
          <span className="field__label">Time</span>
          <input
            className="field__input"
            type="time"
            step={stepMinutes * 60}
            value={clockOf(value)}
            aria-describedby={hintId}
            onChange={(e) => {
              if (e.target.value) commit(`${dateOf(value)}T${e.target.value.slice(0, 5)}`);
            }}
          />
        </label>
      </div>
      <div className="replay__steps">
        <button
          type="button"
          className="button button--secondary"
          disabled={atMin}
          onClick={() => commit(addMinutes(value, -stepMinutes))}
        >
          −{stepMinutes} min
        </button>
        <button
          type="button"
          className="button button--secondary"
          disabled={atMax}
          onClick={() => commit(addMinutes(value, stepMinutes))}
        >
          +{stepMinutes} min
        </button>
      </div>
      <p id={hintId} className="field__hint">
        Recorded data from {dateOf(bounds.min)} to {dateOf(bounds.max)}. Only readings up to the replay time are
        used.
      </p>
    </section>
  );
}
