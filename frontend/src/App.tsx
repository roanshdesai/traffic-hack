import { useCallback, useEffect, useRef, useState } from "react";
import { fetchJourneys, fetchMeta } from "./api/client";
import type { JourneyQuery } from "./api/client";
import type { JourneyResponse, MetaResponse } from "./api/types";
import { DataQualityPanel } from "./components/DataQualityPanel";
import { Disclaimers } from "./components/Disclaimers";
import { ErrorState } from "./components/ErrorState";
import { Results } from "./components/Results";
import { SearchForm } from "./components/SearchForm";
import { SimulatedBanner } from "./components/SimulatedBanner";
import { nowInDelhi } from "./lib/format";

type MetaState =
  | { kind: "loading" }
  | { kind: "ready"; meta: MetaResponse }
  | { kind: "error"; error: unknown };

type SearchState =
  | { kind: "idle" }
  | { kind: "loading" }
  | { kind: "ready"; response: JourneyResponse; key: number }
  | { kind: "error"; error: unknown; query: JourneyQuery };

function formDefaults(meta: MetaResponse | null): { date: string; time: string } {
  const now = nowInDelhi();
  return {
    date: meta?.suggested_query?.date ?? now.date,
    time: meta?.suggested_query?.time ?? now.time,
  };
}

export default function App() {
  const [metaState, setMetaState] = useState<MetaState>({ kind: "loading" });
  const [search, setSearch] = useState<SearchState>({ kind: "idle" });
  const searchCounter = useRef(0);

  const loadMeta = useCallback(() => {
    const controller = new AbortController();
    setMetaState({ kind: "loading" });
    fetchMeta(controller.signal)
      .then((meta) => setMetaState({ kind: "ready", meta }))
      .catch((error: unknown) => {
        if (controller.signal.aborted) return;
        setMetaState({ kind: "error", error });
      });
    return controller;
  }, []);

  useEffect(() => {
    const controller = loadMeta();
    return () => controller.abort();
  }, [loadMeta]);

  const runSearch = useCallback((query: JourneyQuery) => {
    const id = ++searchCounter.current;
    setSearch({ kind: "loading" });
    fetchJourneys(query)
      .then((response) => {
        if (id === searchCounter.current) setSearch({ kind: "ready", response, key: id });
      })
      .catch((error: unknown) => {
        if (id === searchCounter.current) setSearch({ kind: "error", error, query });
      });
  }, []);

  const meta = metaState.kind === "ready" ? metaState.meta : null;
  const response = search.kind === "ready" ? search.response : null;
  // The banner follows the most specific source we have: the journey response, else the dataset meta.
  const provenance = response?.provenance ?? meta?.provenance ?? null;
  const disclaimers = response?.disclaimers ?? meta?.disclaimers ?? [];
  const roadTraffic = response?.road_traffic ?? meta?.road_traffic ?? null;
  const defaults = formDefaults(meta);

  return (
    <div className="app">
      <SimulatedBanner provenance={provenance} />
      <header className="app__header">
        <h1 className="app__title">Delhi Bus Journey Planner</h1>
        <p className="app__tagline">
          Compare the fastest, a balanced and a less crowded bus journey. Prototype.
        </p>
        {provenance && <p className="app__dataset">Dataset: {provenance.label}</p>}
      </header>

      <main className="app__main">
        {metaState.kind === "loading" && (
          <p className="loading" role="status">
            Loading…
          </p>
        )}
        {metaState.kind === "error" && <ErrorState error={metaState.error} onRetry={loadMeta} />}
        {metaState.kind !== "loading" && (
          <SearchForm
            key={metaState.kind}
            initialDate={defaults.date}
            initialTime={defaults.time}
            busy={search.kind === "loading"}
            onSearch={runSearch}
          />
        )}

        <div aria-live="polite">
          {search.kind === "loading" && (
            <p className="loading" role="status">
              Finding scheduled journeys…
            </p>
          )}
        </div>
        {search.kind === "error" && <ErrorState error={search.error} onRetry={() => runSearch(search.query)} />}
        {search.kind === "ready" && <Results key={search.key} response={search.response} periods={meta?.periods} />}

        {metaState.kind === "ready" && <DataQualityPanel />}
      </main>

      <Disclaimers disclaimers={disclaimers} roadTraffic={roadTraffic} fallbacks={meta?.fallbacks ?? []} />
    </div>
  );
}
