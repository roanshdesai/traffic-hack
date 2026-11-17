import { useId } from "react";
import type { Forecast, SimulatedEvent, Site, WindowAssessment } from "../../api/warningTypes";
import { clockOf, dateOf, formatNumber, minuteOfDay, STATUS_LABEL } from "../../lib/warningFormat";

interface Props {
  site: Site;
  date: string;
  windows: WindowAssessment[];
  /** Replay time. Windows after it are greyed: the model could not see them at that moment. */
  at: string;
  forecasts: Forecast[];
  /** Ground truth of synthetic data. Pass an empty list for real data. */
  simulatedEvents: SimulatedEvent[];
}

const W = 520;
const H = 240;
const L = 40;
const R = 10;
const T = 22;
const B = 26;
const PW = W - L - R;
const PH = H - T - B;

function niceMax(value: number): number {
  if (value <= 0) return 10;
  const magnitude = 10 ** Math.floor(Math.log10(value));
  for (const m of [1, 1.5, 2, 2.5, 3, 4, 5, 6, 8, 10]) {
    if (m * magnitude >= value) return m * magnitude;
  }
  return 10 * magnitude;
}

/** Day chart drawn as inline SVG: observed counts, usual range, alerts, replay time, forecast. */
export function TimelineChart({ site, date, windows, at, forecasts, simulatedEvents }: Props) {
  const uid = useId().replace(/:/g, "");
  const n = windows.length;
  if (n === 0) return <p className="muted">No recorded windows for this day.</p>;

  const win = site.window_minutes;
  const dayStart = minuteOfDay(windows[0].window_start);
  const span = n * win;
  const xOfMinute = (m: number) => L + (Math.min(Math.max(m - dayStart, 0), span) / span) * PW;
  const xOfStamp = (stamp: string) => {
    const d = dateOf(stamp);
    if (d < date) return L;
    if (d > date) return L + PW;
    return xOfMinute(minuteOfDay(stamp));
  };
  const bw = PW / n;

  const sameDayForecasts = forecasts.filter((f) => dateOf(f.window_start) === date);
  const candidates: number[] = [1];
  for (const w of windows) {
    if (w.observed !== null) candidates.push(w.observed);
    if (w.baseline) candidates.push(w.baseline.high);
  }
  for (const f of sameDayForecasts) {
    if (f.high !== null) candidates.push(f.high);
    if (f.predicted !== null) candidates.push(f.predicted);
  }
  if (site.alert_threshold !== null) candidates.push(site.alert_threshold);
  const yMax = niceMax(Math.max(...candidates) * 1.05);
  const y = (v: number) => T + PH - (Math.max(v, 0) / yMax) * PH;

  // The replay moment: the end of the window that starts at `at` (data up to then is known).
  const atDate = dateOf(at);
  const replayX = atDate < date ? L : atDate > date ? L + PW : xOfMinute(minuteOfDay(at) + win);
  const isAfter = (w: WindowAssessment) => w.window_start > at;

  // Usual band and median as runs of consecutive windows that have a baseline.
  const runs: Array<Array<{ x: number; w: WindowAssessment }>> = [];
  windows.forEach((w, i) => {
    const point = { x: L + (i + 0.5) * bw, w };
    if (!w.baseline) return;
    const last = runs[runs.length - 1];
    if (last && windows[i - 1]?.baseline) last.push(point);
    else runs.push([point]);
  });

  const alerts = windows.filter((w) => w.status === "overcrowding_alert").length;
  const gaps = windows.filter((w) => w.status === "no_data").length;
  const hourTicks: number[] = [];
  for (let m = Math.ceil(dayStart / 120) * 120; m <= dayStart + span; m += 120) hourTicks.push(m);

  return (
    <figure className="chart">
      <svg
        viewBox={`0 0 ${W} ${H}`}
        className="chart__svg"
        role="img"
        aria-labelledby={`${uid}-t ${uid}-d`}
        data-testid="timeline-chart"
      >
        <title id={`${uid}-t`}>
          {site.name}, {date}: {site.unit} per {win} minutes
        </title>
        <desc id={`${uid}-d`}>
          {n} windows, {alerts} at overcrowding alert, {gaps} without data. Shaded band is the usual range.
        </desc>
        <defs>
          <pattern id={`${uid}-hatch`} width="6" height="6" patternUnits="userSpaceOnUse" patternTransform="rotate(45)">
            <line x1="0" y1="0" x2="0" y2="6" className="chart__hatch-line" />
          </pattern>
          <pattern id={`${uid}-ev`} width="8" height="8" patternUnits="userSpaceOnUse" patternTransform="rotate(-45)">
            <line x1="0" y1="0" x2="0" y2="8" className="chart__event-line" />
          </pattern>
        </defs>

        {/* gridlines + y labels */}
        {[0, 0.5, 1].map((f) => (
          <g key={f}>
            <line x1={L} x2={L + PW} y1={y(yMax * f)} y2={y(yMax * f)} className="chart__grid" />
            <text x={L - 4} y={y(yMax * f) + 4} className="chart__axis" textAnchor="end">
              {formatNumber(yMax * f)}
            </text>
          </g>
        ))}
        {hourTicks.map((m) => (
          <text key={m} x={xOfMinute(m)} y={H - 8} className="chart__axis" textAnchor="middle">
            {`${String(Math.floor(m / 60) % 24).padStart(2, "0")}:00`}
          </text>
        ))}

        {/* simulated ground-truth events */}
        {simulatedEvents.map((ev, i) => {
          const x1 = xOfStamp(ev.start);
          const x2 = Math.max(xOfStamp(ev.end), x1 + 2);
          return (
            <g key={`ev-${i}`} className="chart__event">
              <rect x={x1} y={T} width={x2 - x1} height={PH} fill={`url(#${uid}-ev)`} className="chart__event-band" />
              <text x={x1 + 2} y={T - 8} className="chart__event-label">
                Simulated test event
              </text>
            </g>
          );
        })}

        {/* usual range band and median */}
        {runs.map((run, i) => {
          const upper = run.map((p) => `${p.x},${y(p.w.baseline!.high)}`);
          const lower = [...run].reverse().map((p) => `${p.x},${y(p.w.baseline!.low)}`);
          return (
            <g key={`run-${i}`}>
              <polygon points={[...upper, ...lower].join(" ")} className="chart__band" />
              <polyline points={run.map((p) => `${p.x},${y(p.w.baseline!.median)}`).join(" ")} className="chart__median" />
            </g>
          );
        })}

        {/* observed counts */}
        {windows.map((w, i) => {
          const x = L + i * bw + bw * 0.12;
          const width = Math.max(bw * 0.76, 1);
          const after = isAfter(w) ? " chart__bar--after" : "";
          if (w.status === "no_data" || w.observed === null) {
            return (
              <rect
                key={w.window_start}
                x={x}
                y={T}
                width={width}
                height={PH}
                fill={`url(#${uid}-hatch)`}
                className={`chart__gap${after}`}
              >
                <title>{`${clockOf(w.window_start)}: ${STATUS_LABEL.no_data}`}</title>
              </rect>
            );
          }
          return (
            <rect
              key={w.window_start}
              x={x}
              y={y(w.observed)}
              width={width}
              height={Math.max(T + PH - y(w.observed), 0.5)}
              className={`chart__bar chart__bar--${w.status}${after}`}
            >
              <title>{`${clockOf(w.window_start)}: ${w.observed} ${site.unit} (${STATUS_LABEL[w.status]})`}</title>
            </rect>
          );
        })}

        {/* alert markers */}
        {windows.map((w, i) =>
          w.status === "overcrowding_alert" ? (
            <text key={`a-${w.window_start}`} x={L + (i + 0.5) * bw} y={T + 10} className="chart__alert-mark" textAnchor="middle">
              ‼
            </text>
          ) : null,
        )}

        {/* operator threshold */}
        {site.alert_threshold !== null && (
          <g>
            <line x1={L} x2={L + PW} y1={y(site.alert_threshold)} y2={y(site.alert_threshold)} className="chart__threshold" />
            <text x={L + PW - 2} y={y(site.alert_threshold) - 4} className="chart__axis" textAnchor="end">
              operator threshold {site.alert_threshold}
            </text>
          </g>
        )}

        {/* after replay time */}
        {replayX < L + PW && (
          <g>
            <rect x={replayX} y={T} width={L + PW - replayX} height={PH} className="chart__after" />
            <text x={Math.min(replayX + 4, L + PW - 4)} y={T + PH - 6} className="chart__axis" textAnchor={replayX > L + PW - 120 ? "end" : "start"}>
              after replay time
            </text>
          </g>
        )}

        {/* forecast */}
        {sameDayForecasts.map((f) => {
          if (f.predicted === null) return null;
          const cx = xOfMinute(minuteOfDay(f.window_start) + win / 2);
          return (
            <g key={`f-${f.horizon_min}`} className="chart__forecast">
              {f.low !== null && f.high !== null && <line x1={cx} x2={cx} y1={y(f.low)} y2={y(f.high)} />}
              <circle cx={cx} cy={y(f.predicted)} r={3.5} />
            </g>
          );
        })}

        {/* replay line */}
        {atDate === date && (
          <g>
            <line x1={replayX} x2={replayX} y1={T - 4} y2={T + PH} className="chart__replay" />
            <text x={replayX} y={T - 8} className="chart__replay-label" textAnchor={replayX > L + PW - 80 ? "end" : "middle"}>
              {clockOf(at)}
            </text>
          </g>
        )}
      </svg>
      <figcaption>
        <ul className="legend">
          <li><span className="legend__key legend__key--bar" aria-hidden="true" /> Observed ({site.unit})</li>
          <li><span className="legend__key legend__key--band" aria-hidden="true" /> Usual range</li>
          <li><span className="legend__key legend__key--median" aria-hidden="true" /> Usual (median)</li>
          <li><span aria-hidden="true">‼</span> Overcrowding alert</li>
          <li><span className="legend__key legend__key--gap" aria-hidden="true" /> No data</li>
          <li><span className="legend__key legend__key--after" aria-hidden="true" /> After replay time</li>
          <li><span className="legend__key legend__key--forecast" aria-hidden="true" /> Forecast (estimate)</li>
          {site.alert_threshold !== null && (
            <li><span className="legend__key legend__key--threshold" aria-hidden="true" /> Operator threshold</li>
          )}
          {simulatedEvents.length > 0 && (
            <li><span className="legend__key legend__key--event" aria-hidden="true" /> Simulated test event</li>
          )}
        </ul>
      </figcaption>
      <details className="chart__data">
        <summary>Show the numbers</summary>
        <div className="table-wrap">
          <table className="table">
            <thead>
              <tr>
                <th scope="col">Window</th>
                <th scope="col">Observed</th>
                <th scope="col">Usual</th>
                <th scope="col">Status</th>
              </tr>
            </thead>
            <tbody>
              {windows.map((w) => (
                <tr key={w.window_start} className={isAfter(w) ? "row--after" : undefined}>
                  <td>{clockOf(w.window_start)}</td>
                  <td>{w.observed ?? "—"}</td>
                  <td>{w.baseline ? formatNumber(w.baseline.median) : "—"}</td>
                  <td>
                    {STATUS_LABEL[w.status]}
                    {isAfter(w) ? " (after replay time)" : ""}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </details>
    </figure>
  );
}
