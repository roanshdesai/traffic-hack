import { useCallback, useState } from "react";
import type { FormEvent } from "react";
import { searchStops } from "../api/client";
import type { JourneyQuery } from "../api/client";
import type { Place } from "../api/types";
import { PlaceInput } from "./PlaceInput";
import type { PlaceValue } from "./PlaceInput";

interface Props {
  initialDate: string;
  initialTime: string;
  busy: boolean;
  onSearch: (query: JourneyQuery) => void;
  /** Injectable for tests; defaults to GET /api/stops. */
  searchPlaces?: (query: string, signal: AbortSignal) => Promise<Place[]>;
}

const EMPTY: PlaceValue = { text: "", place: null };

async function defaultSearchPlaces(query: string, signal: AbortSignal): Promise<Place[]> {
  const response = await searchStops(query, 8, signal);
  return response.places;
}

/** Origin, destination, date and time. Submits place ids to the journey API. */
export function SearchForm({ initialDate, initialTime, busy, onSearch, searchPlaces = defaultSearchPlaces }: Props) {
  const [origin, setOrigin] = useState<PlaceValue>(EMPTY);
  const [destination, setDestination] = useState<PlaceValue>(EMPTY);
  const [date, setDate] = useState(initialDate);
  const [time, setTime] = useState(initialTime);
  const [showErrors, setShowErrors] = useState(false);

  const search = useCallback(
    (query: string, signal: AbortSignal) => searchPlaces(query, signal),
    [searchPlaces],
  );

  const samePlace =
    origin.place !== null && destination.place !== null && origin.place.place_id === destination.place.place_id;
  const originError = showErrors && !origin.place ? "Choose a starting stop from the list." : null;
  const destinationError =
    showErrors && !destination.place
      ? "Choose a destination stop from the list."
      : showErrors && samePlace
        ? "Origin and destination are the same place."
        : null;

  function swap() {
    setOrigin(destination);
    setDestination(origin);
  }

  function submit(event: FormEvent) {
    event.preventDefault();
    if (!origin.place || !destination.place || samePlace || !date || !time) {
      setShowErrors(true);
      return;
    }
    setShowErrors(false);
    onSearch({ from: origin.place.place_id, to: destination.place.place_id, date, time });
  }

  return (
    <form className="card search" onSubmit={submit} noValidate aria-label="Plan a bus journey">
      <div className="search__places">
        <PlaceInput
          id="origin"
          label="From"
          placeholder="Starting stop"
          value={origin}
          onChange={setOrigin}
          search={search}
          error={originError}
        />
        <button
          type="button"
          className="button button--icon search__swap"
          onClick={swap}
          aria-label="Swap origin and destination"
          title="Swap origin and destination"
        >
          <span aria-hidden="true">⇅</span>
        </button>
        <PlaceInput
          id="destination"
          label="To"
          placeholder="Destination stop"
          value={destination}
          onChange={setDestination}
          search={search}
          error={destinationError}
        />
      </div>

      <div className="search__when">
        <div className="field">
          <label className="field__label" htmlFor="date">
            Date
          </label>
          <input
            id="date"
            className="field__input"
            type="date"
            required
            value={date}
            onChange={(event) => setDate(event.target.value)}
          />
        </div>
        <div className="field">
          <label className="field__label" htmlFor="time">
            Leave after
          </label>
          <input
            id="time"
            className="field__input"
            type="time"
            required
            value={time}
            onChange={(event) => setTime(event.target.value)}
          />
        </div>
      </div>

      <button type="submit" className="button button--primary search__submit" disabled={busy}>
        {busy ? "Searching…" : "Compare journeys"}
      </button>
    </form>
  );
}
