import { useId, useState } from "react";
import type { SiteStatus } from "../../api/warningTypes";
import { QUALITY_TEXT, SOURCE_LABEL, humanizeKind, ratioText, readingText, warningWhen } from "../../lib/warningFormat";
import { EarlyWarningPill, StatusBadge } from "./StatusBadge";

interface Props {
  sites: SiteStatus[];
  totalSites: number;
  onSelect: (siteId: string) => void;
}

function isUrgent(site: SiteStatus): boolean {
  return site.current.status === "overcrowding_alert" || site.early_warning !== null;
}

/** Sites in the order the API returns them (most urgent first), with a name filter. */
export function SiteList({ sites, totalSites, onSelect }: Props) {
  const filterId = useId();
  const [query, setQuery] = useState("");
  const [urgentOnly, setUrgentOnly] = useState(false);
  const q = query.trim().toLowerCase();
  const shown = sites.filter((s) => (!q || s.site.name.toLowerCase().includes(q)) && (!urgentOnly || isUrgent(s)));

  return (
    <section className="sites" aria-labelledby={`${filterId}-title`}>
      <h2 id={`${filterId}-title`} className="section-title">
        Sites
      </h2>
      <div className="sites__filters">
        <label className="field" htmlFor={filterId}>
          <span className="field__label">Filter by name</span>
          <input
            id={filterId}
            className="field__input"
            type="search"
            value={query}
            autoComplete="off"
            onChange={(e) => setQuery(e.target.value)}
          />
        </label>
        <label className="toggle">
          <input type="checkbox" checked={urgentOnly} onChange={(e) => setUrgentOnly(e.target.checked)} />
          <span>Only show alerts and warnings</span>
        </label>
      </div>
      <p className="sites__count">
        Showing {shown.length} of {sites.length} sites
        {totalSites > sites.length ? ` (the ${sites.length} most urgent of ${totalSites})` : ""}.
      </p>
      {shown.length === 0 ? (
        <p className="card card--empty">No sites match.</p>
      ) : (
        <ul className="site-list">
          {shown.map((s) => (
            <li key={s.site.site_id}>
              <button
                type="button"
                className={`site-card site-card--${s.current.status}${s.early_warning ? " site-card--warning" : ""}`}
                onClick={() => onSelect(s.site.site_id)}
                data-testid="site-card"
              >
                <span className="site-card__top">
                  <span className="site-card__name">{s.site.name}</span>
                  <StatusBadge status={s.current.status} size="sm" />
                </span>
                <span className="site-card__meta">
                  {humanizeKind(s.site.kind)} · <span className="source-badge">{SOURCE_LABEL[s.site.source]}</span>
                </span>
                <span className="site-card__reading">
                  {readingText(s.site, s.current)}
                  {s.current.ratio !== null && s.current.observed !== null && ` (${ratioText(s.current.ratio)})`}
                </span>
                {s.current.baseline && (
                  <span className="site-card__quality">{QUALITY_TEXT[s.current.baseline.quality]}</span>
                )}
                {s.early_warning && (
                  <span className="site-card__warning">
                    <EarlyWarningPill />
                    <span>{warningWhen(s.early_warning.expected_at, s.early_warning.lead_min)}</span>
                    <span className="site-card__warning-summary">{s.early_warning.summary}</span>
                  </span>
                )}
              </button>
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}
