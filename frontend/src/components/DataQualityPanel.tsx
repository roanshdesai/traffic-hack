import { useState } from "react";
import { fetchDataQuality } from "../api/client";
import type { BlockedItem, DataQualityReport, QualityIssue, QualitySection } from "../api/types";
import type { WarningDataQualityReport, WarningQualitySource } from "../api/warningTypes";
import { humanize } from "../lib/format";
import { ErrorState } from "./ErrorState";

type AnyReport = DataQualityReport | WarningDataQualityReport;

interface Props {
  /** Defaults to the planner report (GET /api/planner/data-quality). The monitor passes its own loader. */
  load?: () => Promise<AnyReport>;
}

function isWarningReport(report: AnyReport): report is WarningDataQualityReport {
  return Array.isArray((report as { sources?: unknown }).sources);
}

function IssueList({ issues }: { issues: QualityIssue[] }) {
  if (issues.length === 0) return <p className="dq__none">No issues reported.</p>;
  return (
    <ul className="dq__issues">
      {issues.map((issue, i) => (
        <li key={`${issue.code}-${i}`} className={`dq__issue dq__issue--${issue.severity}`}>
          <span className="dq__severity">{issue.severity}</span>
          <span className="dq__issue-body">
            <code>{issue.code}</code> × {issue.count}
            {issue.file ? ` (${issue.file})` : ""}
            <span className="dq__issue-message">{issue.message}</span>
          </span>
        </li>
      ))}
    </ul>
  );
}

function SectionBlock({ title, section }: { title: string; section: QualitySection | undefined }) {
  if (!section) {
    return (
      <section className="dq__section">
        <h4>{title}</h4>
        <p className="dq__none">Not included in this report.</p>
      </section>
    );
  }
  const summary = section.summary;
  return (
    <section className="dq__section">
      <h4>{title}</h4>
      {summary && (
        <p className="dq__counts">
          <span className="dq__count dq__count--error">{summary.errors} errors</span>
          <span className="dq__count dq__count--warning">{summary.warnings} warnings</span>
          <span className="dq__count dq__count--info">{summary.infos} notes</span>
        </p>
      )}
      <IssueList issues={section.issues ?? []} />
    </section>
  );
}

function BlockedList({ blocked }: { blocked: BlockedItem[] }) {
  return (
    <section className="dq__section">
      <h4>Blocked</h4>
      {blocked.length === 0 ? (
        <p className="dq__none">Nothing is listed as blocked.</p>
      ) : (
        <ul className="dq__blocked">
          {blocked.map((item, i) => (
            <li key={i}>{blockedText(item)}</li>
          ))}
        </ul>
      )}
    </section>
  );
}

function scalar(value: unknown): string | null {
  if (typeof value === "number" || typeof value === "string" || typeof value === "boolean") return String(value);
  return null;
}

/** Report of the early-warning build: one section per input source, plus model notes. */
function WarningReportView({ report }: { report: WarningDataQualityReport }) {
  const modelEntries = Object.entries(report.model ?? {})
    .map(([key, value]) => [key, scalar(value)] as const)
    .filter((entry): entry is readonly [string, string] => entry[1] !== null);
  return (
    <div className="dq__report" data-testid="dq-report">
      {report.generated_at && <p className="dq__generated">Report generated {report.generated_at}</p>}
      {report.sources.length === 0 && <p className="dq__none">No input sources are listed.</p>}
      {report.sources.map((source: WarningQualitySource, i) => {
        const title = [source.name, source.kind ? humanize(source.kind) : null].filter(Boolean).join(" · ") || `Source ${i + 1}`;
        return (
          <section className="dq__section" key={`${source.name ?? "source"}-${i}`}>
            <h4>{title}</h4>
            {(typeof source.rows_total === "number" || typeof source.rows_valid === "number") && (
              <p className="dq__counts">
                {typeof source.rows_total === "number" && <span className="dq__count">{source.rows_total} rows</span>}
                {typeof source.rows_valid === "number" && <span className="dq__count">{source.rows_valid} usable</span>}
              </p>
            )}
            {source.summary && (
              <p className="dq__counts">
                <span className="dq__count dq__count--error">{source.summary.errors} errors</span>
                <span className="dq__count dq__count--warning">{source.summary.warnings} warnings</span>
                <span className="dq__count dq__count--info">{source.summary.infos} notes</span>
              </p>
            )}
            <IssueList issues={(source.issues ?? []) as QualityIssue[]} />
          </section>
        );
      })}
      {modelEntries.length > 0 && (
        <section className="dq__section">
          <h4>Model</h4>
          <ul className="dq__statuses">
            {modelEntries.map(([key, value]) => (
              <li key={key}>
                <span>{humanize(key)}</span>
                <span>{value}</span>
              </li>
            ))}
          </ul>
        </section>
      )}
      <BlockedList blocked={(report.blocked ?? []) as BlockedItem[]} />
    </div>
  );
}

function blockedText(item: BlockedItem): string {
  if (typeof item === "string") return item;
  const title = typeof item.title === "string" ? item.title : typeof item.code === "string" ? humanize(item.code) : "";
  const message = typeof item.message === "string" ? item.message : "";
  if (title && message) return `${title}: ${message}`;
  return title || message || JSON.stringify(item);
}

/** Share of ticket records matched to a route and stops. Accepts 0..1 (or an already-scaled 0..100). */
function matchRateText(rate: number): string {
  const pct = rate <= 1 ? rate * 100 : rate;
  return `${pct.toFixed(1)}% of ticket records matched`;
}

function ReportView({ report }: { report: DataQualityReport }) {
  const matching = report.matching;
  const byStatus = Object.entries(matching?.by_status ?? {});
  const blocked = report.blocked ?? [];
  return (
    <div className="dq__report" data-testid="dq-report">
      {report.generated_at && <p className="dq__generated">Report generated {report.generated_at}</p>}
      <SectionBlock title="GTFS timetable" section={report.gtfs} />
      <SectionBlock title="Ticket samples" section={report.tickets} />
      <section className="dq__section">
        <h4>Route and stop matching</h4>
        {matching ? (
          <>
            <p className="dq__counts">
              {typeof matching.total === "number" && <span className="dq__count">{matching.total} ticket records</span>}
              {typeof matching.match_rate === "number" && (
                <span className="dq__count">{matchRateText(matching.match_rate)}</span>
              )}
            </p>
            {byStatus.length > 0 && (
              <ul className="dq__statuses">
                {byStatus.map(([status, count]) => (
                  <li key={status}>
                    <span>{humanize(status)}</span>
                    <span>{count}</span>
                  </li>
                ))}
              </ul>
            )}
            <p className="dq__none">Ambiguous or invalid records are flagged for review, never guessed.</p>
          </>
        ) : (
          <p className="dq__none">Not included in this report.</p>
        )}
      </section>
      <BlockedList blocked={blocked} />
    </div>
  );
}

/** Collapsible summary of the pipeline's data-quality report. Loads on first open. */
export function DataQualityPanel({ load = () => fetchDataQuality() }: Props) {
  const [state, setState] = useState<
    { kind: "idle" } | { kind: "loading" } | { kind: "ready"; report: AnyReport } | { kind: "error"; error: unknown }
  >({ kind: "idle" });

  function fetchReport() {
    setState({ kind: "loading" });
    load()
      .then((report) => setState({ kind: "ready", report }))
      .catch((error: unknown) => setState({ kind: "error", error }));
  }

  return (
    <details
      className="card dq"
      onToggle={(event) => {
        if (event.currentTarget.open && state.kind === "idle") fetchReport();
      }}
    >
      <summary className="dq__summary">Data quality</summary>
      <div className="dq__content">
        {state.kind === "loading" && <p className="dq__none">Loading the data-quality report…</p>}
        {state.kind === "error" && <ErrorState error={state.error} onRetry={fetchReport} />}
        {state.kind === "ready" &&
          (isWarningReport(state.report) ? (
            <WarningReportView report={state.report} />
          ) : (
            <ReportView report={state.report} />
          ))}
      </div>
    </details>
  );
}
