import type { Status } from "../../api/warningTypes";
import { STATUS_ICON, STATUS_LABEL } from "../../lib/warningFormat";

interface Props {
  counts: Record<string, number>;
}

const ORDER: Array<Status | "early_warning"> = [
  "overcrowding_alert",
  "early_warning",
  "elevated",
  "normal",
  "insufficient_evidence",
  "no_data",
];

/** Number of sites in each state at the replay time. */
export function StatusChips({ counts }: Props) {
  return (
    <ul className="chips" aria-label="Sites by status">
      {ORDER.map((key) => {
        const label = key === "early_warning" ? "Early warning" : STATUS_LABEL[key];
        const icon = key === "early_warning" ? "◷" : STATUS_ICON[key];
        return (
          <li key={key} className={`chip chip--${key}`} data-testid={`chip-${key}`}>
            <span aria-hidden="true">{icon}</span>
            <span className="chip__label">{label}</span>
            <strong className="chip__count">{counts[key] ?? 0}</strong>
          </li>
        );
      })}
    </ul>
  );
}
