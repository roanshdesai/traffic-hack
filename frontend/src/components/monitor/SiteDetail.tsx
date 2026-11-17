import { useEffect, useState } from "react";
import type { SiteStatus, TimelineResponse, Trigger, WarningProvenance } from "../../api/warningTypes";
import { fetchTimeline } from "../../api/warningClient";
import {
  QUALITY_TEXT,
  SOURCE_LABEL,
  dateOf,
  humanizeKind,
  ratioText,
  readingText,
  warningWhen,
} from "../../lib/warningFormat";
import { ErrorState } from "../ErrorState";
import { AlertEpisodeItem } from "./AlertEpisodes";
import { ForecastTable } from "./ForecastTable";
import { EarlyWarningPill, StatusBadge } from "./StatusBadge";
import { TimelineChart } from "./TimelineChart";

interface Props {
  siteId: string;
  /** The site's status at the replay time, if it is in the overview. */
  status: SiteStatus | null;
  at: string;
  provenance: WarningProvenance;
  onBack: () => void;
}

function triggerText(trigger: Trigger, threshold: number | null): string {
  if (trigger === "relative") return "Far above this place's own history for this time.";
  return `At or above the operator-set threshold of ${threshold ?? "?"} (a setting, not a verified capacity).`;
}

/** One site: current reading and reasons, forecast, the day's chart and its alert episodes. */
export function SiteDetail({ siteId, status, at, provenance, onBack }: Props) {
  const date = dateOf(at);
  const [state, setState] = useState<
    { kind: "loading" } | { kind: "ready"; timeline: TimelineResponse } | { kind: "error"; error: unknown }
  >({ kind: "loading" });
  const [attempt, setAttempt] = useState(0);

  useEffect(() => {
    const controller = new AbortController();
    setState((prev) => (prev.kind === "ready" && prev.timeline.date === date ? prev : { kind: "loading" }));
    fetchTimeline(siteId, date, controller.signal)
      .then((timeline) => setState({ kind: "ready", timeline }))
      .catch((error: unknown) => {
        if (!controller.signal.aborted) setState({ kind: "error", error });
      });
    return () => controller.abort();
  }, [siteId, date, attempt]);

  const timeline = state.kind === "ready" ? state.timeline : null;
  const site = status?.site ?? timeline?.site ?? null;
  const current = status?.current ?? null;
  const events = provenance.simulated && timeline ? timeline.simulated_events : [];

  return (
    <section className="detail" aria-labelledby="detail-title">
      <button type="button" className="button button--secondary detail__back" onClick={onBack}>
        ← All sites
      </button>
      <div className="card detail__card">
        <h2 id="detail-title" className="detail__title">
          {site?.name ?? siteId}
        </h2>
        {site && (
          <p className="detail__meta">
            {humanizeKind(site.kind)} · <span className="source-badge">{SOURCE_LABEL[site.source]}</span> · counted per{" "}
            {site.window_minutes} min
            {site.coverage === "sample" && " · a sample of passengers, not a headcount"}
          </p>
        )}

        {status && site && current ? (
          <>
            <div className="detail__status">
              <StatusBadge status={current.status} />
              <span className="detail__reading">
                {readingText(site, current)}
                {current.ratio !== null && current.observed !== null && ` (${ratioText(current.ratio)})`}
              </span>
            </div>
            {current.baseline && (
              <p className="muted small">
                Usual range {Math.round(current.baseline.low)}–{Math.round(current.baseline.high)} from{" "}
                {current.baseline.support_days} days of history · {QUALITY_TEXT[current.baseline.quality]}
              </p>
            )}
            {status.early_warning && (
              <div className="detail__warning" role="status">
                <EarlyWarningPill />
                <p>
                  <strong>{warningWhen(status.early_warning.expected_at, status.early_warning.lead_min)}</strong>
                </p>
                <p>{status.early_warning.summary}</p>
              </div>
            )}
            {current.triggers.length > 0 && (
              <div>
                <h3 className="subsection-title">Why this is an alert</h3>
                <ul className="reason__details">
                  {current.triggers.map((t) => (
                    <li key={t}>{triggerText(t, site.alert_threshold)}</li>
                  ))}
                </ul>
              </div>
            )}
            {current.reasons.length > 0 && (
              <div>
                <h3 className="subsection-title">Reasons</h3>
                <ul className="reason__details">
                  {current.reasons.map((r, i) => (
                    <li key={i}>{r}</li>
                  ))}
                </ul>
              </div>
            )}
            <ForecastTable forecasts={status.forecasts} unit={site.unit} />
          </>
        ) : (
          <p className="muted">This site is not in the current overview; showing its day only.</p>
        )}
      </div>

      <div className="card">
        <h3 className="subsection-title">The day at this site ({date})</h3>
        {state.kind === "loading" && (
          <p className="loading" role="status">
            Loading the day…
          </p>
        )}
        {state.kind === "error" && <ErrorState error={state.error} onRetry={() => setAttempt((n) => n + 1)} />}
        {timeline && site && (
          <>
            <TimelineChart
              site={site}
              date={timeline.date}
              windows={timeline.windows}
              at={at}
              forecasts={status?.forecasts ?? []}
              simulatedEvents={events}
            />
            <h3 className="subsection-title">Alert episodes this day</h3>
            {timeline.episodes.length === 0 ? (
              <p className="muted">No overcrowding alerts at this site on this day.</p>
            ) : (
              <ul className="episodes">
                {timeline.episodes.map((e, i) => (
                  <AlertEpisodeItem
                    key={`${e.start}-${i}`}
                    episode={e}
                    simulated={provenance.simulated}
                    unit={site.unit}
                    showSite={false}
                  />
                ))}
              </ul>
            )}
          </>
        )}
      </div>
    </section>
  );
}
