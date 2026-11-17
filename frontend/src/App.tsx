import { useCallback, useEffect, useState } from "react";
import type { WarningMeta } from "./api/warningTypes";
import { fetchWarningMeta } from "./api/warningClient";
import { ErrorState } from "./components/ErrorState";
import { MonitorView } from "./components/monitor/MonitorView";
import { SimulatedBanner, WARNING_SIMULATED_TEXT } from "./components/SimulatedBanner";
import { PlannerView } from "./planner/PlannerView";

type View = "monitor" | "planner";

type MetaState = { kind: "loading" } | { kind: "ready"; meta: WarningMeta } | { kind: "error"; error: unknown };

/** App shell. The overcrowding monitor is the product; the journey planner is a secondary view. */
export default function App() {
  const [view, setView] = useState<View>("monitor");
  const [metaState, setMetaState] = useState<MetaState>({ kind: "loading" });

  const loadMeta = useCallback(() => {
    const controller = new AbortController();
    setMetaState({ kind: "loading" });
    fetchWarningMeta(controller.signal)
      .then((meta) => setMetaState({ kind: "ready", meta }))
      .catch((error: unknown) => {
        if (!controller.signal.aborted) setMetaState({ kind: "error", error });
      });
    return controller;
  }, []);

  useEffect(() => {
    const controller = loadMeta();
    return () => controller.abort();
  }, [loadMeta]);

  const meta = metaState.kind === "ready" ? metaState.meta : null;

  return (
    <div className="app">
      {view === "monitor" && <SimulatedBanner provenance={meta?.provenance} text={WARNING_SIMULATED_TEXT} />}
      <header className="app__header">
        <h1 className="app__title">Overcrowding Early Warning (prototype)</h1>
        <nav className="nav" aria-label="Views">
          <button
            type="button"
            className={`nav__item${view === "monitor" ? " nav__item--on" : ""}`}
            aria-current={view === "monitor" ? "page" : undefined}
            onClick={() => setView("monitor")}
          >
            Overcrowding monitor
          </button>
          <button
            type="button"
            className={`nav__item${view === "planner" ? " nav__item--on" : ""}`}
            aria-current={view === "planner" ? "page" : undefined}
            onClick={() => setView("planner")}
          >
            Journey planner (secondary)
          </button>
        </nav>
        {view === "monitor" && (
          <>
            <p className="app__tagline app__replay-note">Replay of recorded data, not live.</p>
            {meta && <p className="app__dataset">Dataset: {meta.provenance.label}</p>}
          </>
        )}
      </header>

      {view === "monitor" && (
        <>
          {metaState.kind === "loading" && (
            <main className="app__main">
              <p className="loading" role="status">
                Loading…
              </p>
            </main>
          )}
          {metaState.kind === "error" && (
            <main className="app__main">
              <ErrorState error={metaState.error} onRetry={loadMeta} />
            </main>
          )}
          {meta && <MonitorView meta={meta} />}
        </>
      )}
      {view === "planner" && <PlannerView />}
    </div>
  );
}
