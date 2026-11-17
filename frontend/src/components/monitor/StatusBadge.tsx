import type { Status } from "../../api/warningTypes";
import { STATUS_ICON, STATUS_LABEL } from "../../lib/warningFormat";

interface Props {
  status: Status;
  size?: "sm" | "md";
}

/** Status pill: icon + text + colour. "Not enough history" and "No data" are neutral and hatched. */
export function StatusBadge({ status, size = "md" }: Props) {
  return (
    <span className={`status status--${status} status--${size}`} data-status={status}>
      <span className="status__icon" aria-hidden="true">
        {STATUS_ICON[status]}
      </span>
      <span className="status__label">{STATUS_LABEL[status]}</span>
    </span>
  );
}

/** Distinct pill for a forecast-based early warning. */
export function EarlyWarningPill() {
  return (
    <span className="ew-pill">
      <span aria-hidden="true">◷</span> Early warning
    </span>
  );
}
