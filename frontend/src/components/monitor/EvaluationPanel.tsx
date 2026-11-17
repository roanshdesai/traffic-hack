import { useState } from "react";
import type { EvaluationResponse } from "../../api/warningTypes";
import { fetchEvaluation } from "../../api/warningClient";
import { humanize } from "../../lib/format";
import { metricText } from "../../lib/warningFormat";
import { ErrorState } from "../ErrorState";

interface Props {
  load?: () => Promise<EvaluationResponse>;
}

function MetricList({ metrics }: { metrics: Record<string, unknown> }) {
  const entries = Object.entries(metrics);
  if (entries.length === 0) return <p className="dq__none">No metrics reported.</p>;
  return (
    <dl className="metrics">
      {entries.map(([key, value]) =>
        value && typeof value === "object" && !Array.isArray(value) ? (
          <div key={key} className="metrics__group">
            <dt>{humanize(key)}</dt>
            <dd>
              <MetricList metrics={value as Record<string, unknown>} />
            </dd>
          </div>
        ) : (
          <div key={key} className="metrics__row">
            <dt>{humanize(key)}</dt>
            <dd>{metricText(value)}</dd>
          </div>
        ),
      )}
    </dl>
  );
}

/** Backtest results. Collapsible; loads on first open. */
export function EvaluationPanel({ load = () => fetchEvaluation() }: Props) {
  const [state, setState] = useState<
    { kind: "idle" } | { kind: "loading" } | { kind: "ready"; ev: EvaluationResponse } | { kind: "error"; error: unknown }
  >({ kind: "idle" });

  function fetchIt() {
    setState({ kind: "loading" });
    load()
      .then((ev) => setState({ kind: "ready", ev }))
      .catch((error: unknown) => setState({ kind: "error", error }));
  }

  const heading =
    state.kind === "ready"
      ? state.ev.ground_truth === "simulated_events"
        ? "How well this works on test data"
        : "No ground truth for this data"
      : "How well does this work?";

  return (
    <details
      className="card dq"
      onToggle={(event) => {
        if (event.currentTarget.open && state.kind === "idle") fetchIt();
      }}
    >
      <summary className="dq__summary">{heading}</summary>
      <div className="dq__content">
        {state.kind === "loading" && <p className="dq__none">Loading the evaluation…</p>}
        {state.kind === "error" && <ErrorState error={state.error} onRetry={fetchIt} />}
        {state.kind === "ready" && (
          <div className="dq__report" data-testid="evaluation">
            <h3 className="subsection-title">
              {state.ev.ground_truth === "simulated_events"
                ? "How well this works on test data"
                : "No ground truth for this data"}
            </h3>
            <p className="evaluation__caveat">{state.ev.caveat}</p>
            <MetricList metrics={state.ev.metrics} />
            {state.ev.notes.length > 0 && (
              <ul className="dq__blocked">
                {state.ev.notes.map((note, i) => (
                  <li key={i}>{note}</li>
                ))}
              </ul>
            )}
          </div>
        )}
      </div>
    </details>
  );
}
