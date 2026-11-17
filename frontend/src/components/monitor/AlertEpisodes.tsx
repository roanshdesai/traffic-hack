import { useEffect, useState } from "react";
import type { AlertEpisode, Trigger } from "../../api/warningTypes";
import { fetchAlerts } from "../../api/warningClient";
import { clockOf, ratioText } from "../../lib/warningFormat";
import { ErrorState } from "../ErrorState";

const TRIGGER_SHORT: Record<Trigger, string> = {
  relative: "far above usual",
  threshold: "at or above operator threshold",
};

interface ItemProps {
  episode: AlertEpisode;
  simulated: boolean;
  unit?: string;
  showSite?: boolean;
}

export function AlertEpisodeItem({ episode, simulated, unit, showSite = true }: ItemProps) {
  return (
    <li className="episode" data-testid="alert-episode">
      <p className="episode__head">
        {showSite && <strong>{episode.site_name}</strong>}
        <span>
          {clockOf(episode.start)}–{clockOf(episode.end)}
        </span>
      </p>
      <p className="episode__body">
        Peak {episode.peak_observed}
        {unit ? ` ${unit}` : ""}
        {episode.peak_ratio !== null ? ` (${ratioText(episode.peak_ratio)})` : ""}
        {episode.triggers.length > 0 && ` · ${episode.triggers.map((t) => TRIGGER_SHORT[t]).join(", ")}`}
      </p>
      <p className="episode__body">
        {episode.first_warning_at
          ? `First forecast at ${clockOf(episode.first_warning_at)}${
              episode.lead_min !== null ? ` (${episode.lead_min} min ahead)` : ""
            }`
          : "Not forecast in advance"}
      </p>
      {simulated && episode.matched_event !== null && (
        <p className={`episode__match episode__match--${episode.matched_event ? "yes" : "no"}`}>
          {episode.matched_event
            ? "Matches a simulated test event"
            : "No matching simulated event — a false alarm on test data"}
        </p>
      )}
    </li>
  );
}

interface SectionProps {
  date: string;
  simulated: boolean;
  units: Record<string, string>;
}

/** Alert episodes for one replay day (GET /api/alerts?date=). */
export function AlertsSection({ date, simulated, units }: SectionProps) {
  const [state, setState] = useState<
    { kind: "loading" } | { kind: "ready"; episodes: AlertEpisode[] } | { kind: "error"; error: unknown }
  >({ kind: "loading" });
  const [attempt, setAttempt] = useState(0);

  useEffect(() => {
    const controller = new AbortController();
    setState({ kind: "loading" });
    fetchAlerts(date, controller.signal)
      .then((res) => setState({ kind: "ready", episodes: res.episodes }))
      .catch((error: unknown) => {
        if (!controller.signal.aborted) setState({ kind: "error", error });
      });
    return () => controller.abort();
  }, [date, attempt]);

  return (
    <section className="alerts" aria-labelledby="alerts-title">
      <h2 id="alerts-title" className="section-title">
        Alerts on {date}
      </h2>
      <p className="muted small">The whole recorded day, including times after the replay time.</p>
      {state.kind === "loading" && (
        <p className="loading" role="status">
          Loading alerts…
        </p>
      )}
      {state.kind === "error" && <ErrorState error={state.error} onRetry={() => setAttempt((n) => n + 1)} />}
      {state.kind === "ready" &&
        (state.episodes.length === 0 ? (
          <p className="card card--empty">No overcrowding alerts on this day.</p>
        ) : (
          <ul className="episodes">
            {state.episodes.map((e, i) => (
              <AlertEpisodeItem key={`${e.site_id}-${e.start}-${i}`} episode={e} simulated={simulated} unit={units[e.site_id]} />
            ))}
          </ul>
        ))}
    </section>
  );
}
