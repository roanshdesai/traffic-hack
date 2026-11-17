import type { FallbackInfo, RoadTraffic } from "../api/types";
import { BASIS_LABEL, humanize } from "../lib/format";

interface Props {
  disclaimers: string[];
  roadTraffic: RoadTraffic | null;
  fallbacks?: FallbackInfo[];
}

const ROAD_TRAFFIC_STATUS: Record<RoadTraffic["status"], string> = {
  not_configured: "Not connected",
  unavailable: "Unavailable",
  ok: "Connected",
};

function fallbackLabel(basis: string | undefined): string {
  if (!basis) return "Fallback";
  const known = (BASIS_LABEL as Record<string, string | undefined>)[basis];
  return known ? humanize(known) : humanize(basis);
}

/** Footer: what the numbers mean, how estimates fall back, and the separate road-traffic note. */
export function Disclaimers({ disclaimers, roadTraffic, fallbacks = [] }: Props) {
  return (
    <footer className="footer">
      {disclaimers.length > 0 && (
        <section className="footer__block" aria-label="About these results">
          <h2 className="footer__heading">About these results</h2>
          <ul className="footer__list">
            {disclaimers.map((text, i) => (
              <li key={i}>{text}</li>
            ))}
          </ul>
        </section>
      )}

      {fallbacks.length > 0 && (
        <details className="footer__block footer__details">
          <summary>How crowding estimates fall back when samples are thin</summary>
          <ol className="footer__list">
            {fallbacks.map((fallback, i) => (
              <li key={i}>
                <strong>{fallbackLabel(fallback.basis)}</strong>
                {fallback.description ? `: ${fallback.description}` : ""}
                {fallback.quality_cap ? ` (evidence at most ${fallback.quality_cap})` : ""}
              </li>
            ))}
          </ol>
        </details>
      )}

      {roadTraffic && (
        <section className="footer__block road-traffic" aria-label="Road traffic" data-testid="road-traffic">
          <h2 className="footer__heading">Road traffic (separate signal)</h2>
          <p className="road-traffic__status">
            Status: {ROAD_TRAFFIC_STATUS[roadTraffic.status] ?? roadTraffic.status}
          </p>
          <p>{roadTraffic.note}</p>
          <p className="road-traffic__note">
            Road traffic describes vehicles on roads. It is kept apart from passenger crowding and is not part
            of any crowding level shown above.
          </p>
        </section>
      )}
    </footer>
  );
}
