import { useEffect, useRef, useState } from "react";
import type { KeyboardEvent } from "react";
import type { Place } from "../api/types";

export interface PlaceValue {
  /** What is typed in the box. */
  text: string;
  /** The chosen place, or null until the user picks one from the list. */
  place: Place | null;
}

interface Props {
  id: string;
  label: string;
  value: PlaceValue;
  onChange: (value: PlaceValue) => void;
  /** Looks up places for the typed text (GET /api/stops). */
  search: (query: string, signal: AbortSignal) => Promise<Place[]>;
  placeholder?: string;
  error?: string | null;
}

const DEBOUNCE_MS = 200;

/** Autocomplete for an origin or destination place (ARIA combobox with a listbox popup). */
export function PlaceInput({ id, label, value, onChange, search, placeholder, error }: Props) {
  const [open, setOpen] = useState(false);
  const [results, setResults] = useState<Place[]>([]);
  const [status, setStatus] = useState<"idle" | "loading" | "error">("idle");
  const [active, setActive] = useState(-1);
  const [hasFocus, setHasFocus] = useState(false);
  const listId = `${id}-listbox`;
  const errorId = `${id}-error`;
  const searchRef = useRef(search);
  searchRef.current = search;

  const query = value.text;
  const selectedId = value.place?.place_id ?? null;

  // Debounced lookup while the box has focus and nothing is selected yet.
  useEffect(() => {
    if (!hasFocus || selectedId !== null) return;
    const controller = new AbortController();
    setStatus("loading");
    const timer = window.setTimeout(() => {
      searchRef
        .current(query.trim(), controller.signal)
        .then((places) => {
          if (controller.signal.aborted) return;
          setResults(places);
          setActive(places.length > 0 ? 0 : -1);
          setStatus("idle");
        })
        .catch((err: unknown) => {
          if (controller.signal.aborted) return;
          if (err instanceof DOMException && err.name === "AbortError") return;
          setResults([]);
          setStatus("error");
        });
    }, DEBOUNCE_MS);
    return () => {
      controller.abort();
      window.clearTimeout(timer);
    };
  }, [query, hasFocus, selectedId]);

  function choose(place: Place) {
    onChange({ text: place.name, place });
    setOpen(false);
    setActive(-1);
  }

  function onKeyDown(event: KeyboardEvent<HTMLInputElement>) {
    if (event.key === "ArrowDown") {
      event.preventDefault();
      setOpen(true);
      if (results.length > 0) setActive((i) => (i + 1) % results.length);
    } else if (event.key === "ArrowUp") {
      event.preventDefault();
      if (results.length > 0) setActive((i) => (i <= 0 ? results.length - 1 : i - 1));
    } else if (event.key === "Enter") {
      if (open && active >= 0 && results[active]) {
        event.preventDefault();
        choose(results[active]);
      }
    } else if (event.key === "Escape") {
      setOpen(false);
    }
  }

  const showList = open && selectedId === null;
  const activeOptionId = showList && active >= 0 ? `${id}-option-${active}` : undefined;

  return (
    <div className="field place-input">
      <label className="field__label" htmlFor={id}>
        {label}
      </label>
      <input
        id={id}
        className="field__input"
        type="text"
        role="combobox"
        autoComplete="off"
        autoCapitalize="words"
        spellCheck={false}
        placeholder={placeholder}
        value={value.text}
        aria-autocomplete="list"
        aria-expanded={showList}
        aria-controls={listId}
        aria-activedescendant={activeOptionId}
        aria-invalid={error ? true : undefined}
        aria-describedby={error ? errorId : undefined}
        onChange={(event) => {
          onChange({ text: event.target.value, place: null });
          setOpen(true);
        }}
        onFocus={() => {
          setHasFocus(true);
          setOpen(true);
        }}
        onBlur={() => {
          setHasFocus(false);
          setOpen(false);
        }}
        onKeyDown={onKeyDown}
      />
      {value.place && (
        <p className="field__hint" data-testid={`${id}-selected`}>
          {value.place.routes.length > 0 ? `Routes: ${value.place.routes.join(", ")}` : "No routes listed"}
        </p>
      )}
      {error && (
        <p className="field__error" id={errorId}>
          {error}
        </p>
      )}
      <ul className="place-list" id={listId} role="listbox" aria-label={`${label} suggestions`} hidden={!showList}>
        {showList && status === "loading" && results.length === 0 && (
          <li className="place-list__note" role="presentation">
            Searching…
          </li>
        )}
        {showList && status === "error" && (
          <li className="place-list__note" role="presentation">
            Could not load stops.
          </li>
        )}
        {showList && status === "idle" && results.length === 0 && (
          <li className="place-list__note" role="presentation">
            No stops match “{query.trim()}”.
          </li>
        )}
        {showList &&
          results.map((place, index) => (
            <li
              key={place.place_id}
              id={`${id}-option-${index}`}
              role="option"
              aria-selected={index === active}
              className={`place-list__option ${index === active ? "place-list__option--active" : ""}`}
              // Keep focus in the input so blur does not close the list before the click lands.
              onMouseDown={(event) => event.preventDefault()}
              onClick={() => choose(place)}
              onMouseEnter={() => setActive(index)}
            >
              <span className="place-list__name">{place.name}</span>
              <span className="place-list__routes">
                {place.routes.length > 0 ? `Routes ${place.routes.join(", ")}` : "No routes listed"}
              </span>
            </li>
          ))}
      </ul>
    </div>
  );
}
