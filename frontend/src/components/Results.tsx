import { useState } from "react";
import type { JourneyOption, JourneyResponse, OptionKind, PeriodInfo } from "../api/types";
import { humanize } from "../lib/format";
import { InsufficientEvidence } from "./InsufficientEvidence";
import { JourneyCard } from "./JourneyCard";
import { NoJourney } from "./NoJourney";
import { OptionTabs, panelId, tabId } from "./OptionTabs";

interface Props {
  response: JourneyResponse;
  /** Period definitions from /api/meta, used to label the request's period. */
  periods?: PeriodInfo[];
}

function OptionPanel({ option, onShowFastest }: { option: JourneyOption; onShowFastest: () => void }) {
  if (option.status === "ok" && option.journey) {
    return <JourneyCard option={option} journey={option.journey} />;
  }
  if (option.status === "insufficient_evidence") {
    return <InsufficientEvidence option={option} onShowFastest={onShowFastest} />;
  }
  return (
    <NoJourney
      title={`${option.label}: no scheduled journey`}
      message={option.reason.summary}
      reason={option.reason}
    />
  );
}

/** Results for one search: summary line, the three option tabs and the selected option. */
export function Results({ response, periods = [] }: Props) {
  const [selected, setSelected] = useState<OptionKind>("fastest");
  const { request, options } = response;
  const periodLabel = periods.find((p) => p.id === request.period)?.label ?? humanize(request.period);

  const summary = (
    <header className="results__header">
      <h2 className="results__title">
        {request.origin.name} <span aria-hidden="true">→</span>
        <span className="visually-hidden"> to </span> {request.destination.name}
      </h2>
      <p className="results__meta">
        Departing after {request.time} on {request.date} · {humanize(request.day_type)} · {periodLabel}
      </p>
      <p className="results__message">{response.message}</p>
    </header>
  );

  if (response.status === "no_journey" || options.length === 0) {
    return (
      <section className="results" aria-label="Journey results">
        {summary}
        <NoJourney message={response.message} />
      </section>
    );
  }

  const current = options.find((o) => o.kind === selected) ?? options[0];

  return (
    <section className="results" aria-label="Journey results">
      {summary}
      <OptionTabs options={options} selected={current.kind} onSelect={setSelected} />
      <div role="tabpanel" id={panelId(current.kind)} aria-labelledby={tabId(current.kind)} tabIndex={-1}>
        <OptionPanel option={current} onShowFastest={() => setSelected("fastest")} />
      </div>
    </section>
  );
}
