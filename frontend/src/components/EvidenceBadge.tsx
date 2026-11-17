import type { EvidenceQuality } from "../api/types";
import { QUALITY_LABEL } from "../lib/format";

interface Props {
  quality: EvidenceQuality;
}

/** How much ticket evidence stands behind an estimate. */
export function EvidenceBadge({ quality }: Props) {
  return (
    <span className={`evidence evidence--${quality}`} data-quality={quality}>
      {QUALITY_LABEL[quality]}
    </span>
  );
}
