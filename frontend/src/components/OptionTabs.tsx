import { useRef } from "react";
import type { KeyboardEvent } from "react";
import type { JourneyOption, OptionKind } from "../api/types";
import { formatClock, formatMinutes } from "../lib/format";

interface Props {
  options: JourneyOption[];
  selected: OptionKind;
  onSelect: (kind: OptionKind) => void;
}

export function tabId(kind: OptionKind): string {
  return `option-tab-${kind}`;
}

export function panelId(kind: OptionKind): string {
  return `option-panel-${kind}`;
}

function headline(option: JourneyOption): { main: string; sub: string } {
  if (option.status === "ok" && option.journey) {
    return {
      main: formatMinutes(option.journey.total_min),
      sub: `arrive ${formatClock(option.journey.scheduled_arrival)}`,
    };
  }
  if (option.status === "insufficient_evidence") {
    return { main: "Not enough evidence", sub: "cannot rank" };
  }
  return { main: "No journey", sub: "none scheduled" };
}

/** Segmented control for Fastest / Balanced / Less crowded (ARIA tabs, arrow-key navigation). */
export function OptionTabs({ options, selected, onSelect }: Props) {
  const refs = useRef<Record<string, HTMLButtonElement | null>>({});

  function onKeyDown(event: KeyboardEvent<HTMLButtonElement>, index: number) {
    let next = index;
    if (event.key === "ArrowRight") next = (index + 1) % options.length;
    else if (event.key === "ArrowLeft") next = (index - 1 + options.length) % options.length;
    else if (event.key === "Home") next = 0;
    else if (event.key === "End") next = options.length - 1;
    else return;
    event.preventDefault();
    const kind = options[next].kind;
    onSelect(kind);
    refs.current[kind]?.focus();
  }

  return (
    <div className="tabs" role="tablist" aria-label="Journey options">
      {options.map((option, index) => {
        const isSelected = option.kind === selected;
        const { main, sub } = headline(option);
        return (
          <button
            key={option.kind}
            ref={(el) => {
              refs.current[option.kind] = el;
            }}
            type="button"
            role="tab"
            id={tabId(option.kind)}
            aria-selected={isSelected}
            aria-controls={panelId(option.kind)}
            tabIndex={isSelected ? 0 : -1}
            className={`tab tab--${option.status} ${isSelected ? "tab--selected" : ""}`}
            data-status={option.status}
            onClick={() => onSelect(option.kind)}
            onKeyDown={(event) => onKeyDown(event, index)}
          >
            <span className="tab__label">{option.label}</span>
            <span className="tab__headline">{main}</span>
            <span className="tab__sub">{sub}</span>
          </button>
        );
      })}
    </div>
  );
}
