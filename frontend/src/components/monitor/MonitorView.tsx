import { useEffect, useMemo, useRef, useState } from "react";
import type { OverviewResponse, WarningMeta } from "../../api/warningTypes";
import { fetchOverview, fetchWarningDataQuality } from "../../api/warningClient";
import { clampStamp, dateOf, replayBounds, snapStamp } from "../../lib/warningFormat";
import { DataQualityPanel } from "../DataQualityPanel";
import { Disclaimers } from "../Disclaimers";
import { ErrorState } from "../ErrorState";
import { AlertsSection } from "./AlertEpisodes";
import { EvaluationPanel } from "./EvaluationPanel";
import { ReplayControl } from "./ReplayControl";
import { SiteDetail } from "./SiteDetail";
import { SiteList } from "./SiteList";
import { StatusChips } from "./StatusChips";

interface Props {
  meta: WarningMeta;
}

type OverviewState =
  | { kind: "loading"; previous: OverviewResponse | null }
  | { kind: "ready"; overview: OverviewResponse }
  | { kind: "error"; error: unknown };

/** The main product: every site's status at a replay time, early warnings, and per-site detail. */
export function MonitorView({ meta }: Props) {
  const bounds = useMemo(() => replayBounds(meta.provenance.replay_period), [meta.provenance.replay_period]);
  const [at, setAt] = useState(() => clampStamp(snapStamp(meta.default_at), bounds));
  const [state, setState] = useState<OverviewState>({ kind: "loading", previous: null });
  const [selected, setSelected] = useState<string | null>(null);
  const [tab, setTab] = useState<"sites" | "alerts">("sites");
  const [attempt, setAttempt] = useState(0);
  const lastGood = useRef<OverviewResponse | null>(null);

  useEffect(() => {
    const controller = new AbortController();
    setState({ kind: "loading", previous: lastGood.current });
    fetchOverview(at, controller.signal)
      .then((overview) => {
        lastGood.current = overview;
        setState({ kind: "ready", overview });
      })
      .catch((error: unknown) => {
        if (!controller.signal.aborted) setState({ kind: "error", error });
      });
    return () => controller.abort();
  }, [at, attempt]);

  const overview = state.kind === "ready" ? state.overview : state.kind === "loading" ? state.previous : null;
  const provenance = overview?.provenance ?? meta.provenance;
  const units = useMemo(
    () => Object.fromEntries((overview?.sites ?? []).map((s) => [s.site.site_id, s.site.unit])),
    [overview],
  );
  const selectedStatus = selected ? overview?.sites.find((s) => s.site.site_id === selected) ?? null : null;

  return (
    <>
      <main className="app__main">
        <ReplayControl value={at} bounds={bounds} busy={state.kind === "loading"} onChange={setAt} />

        <div aria-live="polite" className="visually-hidden">
          {state.kind === "loading" ? "Loading the replay time…" : overview ? `Showing ${overview.at}` : ""}
        </div>
        {state.kind === "error" && <ErrorState error={state.error} onRetry={() => setAttempt((n) => n + 1)} />}

        {overview && <StatusChips counts={overview.counts} />}

        {selected ? (
          <SiteDetail
            key={selected}
            siteId={selected}
            status={selectedStatus}
            at={at}
            provenance={provenance}
            onBack={() => setSelected(null)}
          />
        ) : (
          <>
            <div className="segmented" role="group" aria-label="Show">
              <button
                type="button"
                className={`segmented__item${tab === "sites" ? " segmented__item--on" : ""}`}
                aria-pressed={tab === "sites"}
                onClick={() => setTab("sites")}
              >
                Sites now
              </button>
              <button
                type="button"
                className={`segmented__item${tab === "alerts" ? " segmented__item--on" : ""}`}
                aria-pressed={tab === "alerts"}
                onClick={() => setTab("alerts")}
              >
                Alerts this day
              </button>
            </div>
            {tab === "sites" && overview && (
              <SiteList sites={overview.sites} totalSites={overview.total_sites} onSelect={setSelected} />
            )}
            {tab === "sites" && !overview && state.kind === "loading" && (
              <p className="loading" role="status">
                Loading sites…
              </p>
            )}
            {tab === "alerts" && <AlertsSection date={dateOf(at)} simulated={provenance.simulated} units={units} />}
          </>
        )}

        <EvaluationPanel />
        <DataQualityPanel load={() => fetchWarningDataQuality()} />
      </main>

      <Disclaimers
        heading="About these readings"
        disclaimers={overview?.disclaimers ?? meta.disclaimers}
        roadTraffic={overview?.road_traffic ?? meta.road_traffic}
      />
    </>
  );
}
