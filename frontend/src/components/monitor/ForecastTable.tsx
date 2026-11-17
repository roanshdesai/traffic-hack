import type { Forecast } from "../../api/warningTypes";
import { clockOf, formatNumber } from "../../lib/warningFormat";
import { StatusBadge } from "./StatusBadge";

interface Props {
  forecasts: Forecast[];
  unit: string;
}

function predictedText(f: Forecast): string {
  if (f.predicted === null) return "—";
  const range = f.low !== null && f.high !== null ? ` (${formatNumber(f.low)}–${formatNumber(f.high)})` : "";
  return `${formatNumber(f.predicted)}${range}`;
}

/** Short-horizon forecast. Always presented as an estimate. */
export function ForecastTable({ forecasts, unit }: Props) {
  return (
    <section className="forecast" aria-labelledby="forecast-title">
      <h3 id="forecast-title" className="subsection-title">
        Forecast (estimate)
      </h3>
      {forecasts.length === 0 ? (
        <p className="muted">No forecast for this moment.</p>
      ) : (
        <div className="table-wrap">
          <table className="table" data-testid="forecast-table">
            <thead>
              <tr>
                <th scope="col">In</th>
                <th scope="col">Window</th>
                <th scope="col">Predicted ({unit})</th>
                <th scope="col">Usual</th>
                <th scope="col">Status</th>
              </tr>
            </thead>
            <tbody>
              {forecasts.map((f) => (
                <tr key={f.horizon_min}>
                  <td>{f.horizon_min} min</td>
                  <td>{clockOf(f.window_start)}</td>
                  <td>{predictedText(f)}</td>
                  <td>{f.usual === null ? "—" : formatNumber(f.usual)}</td>
                  <td>
                    <StatusBadge status={f.status} size="sm" />
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      <p className="muted small">
        A projection of the recent trend against this place&apos;s usual level, with a likely range. It can be
        wrong, especially when a change starts suddenly.
      </p>
    </section>
  );
}
