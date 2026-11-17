/**
 * MOCK / SIMULATED test data. Hand-written to exercise the UI; it does not come
 * from the backend and does not describe any real route, stop, timetable or crowding.
 */
import type {
  BusLeg,
  DataQualityReport,
  Evidence,
  Journey,
  JourneyResponse,
  MetaResponse,
  Place,
  Provenance,
  Segment,
  TransferLeg,
} from "../api/types";

const DAY = "2026-11-16";
const iso = (hhmm: string) => `${DAY}T${hhmm}:00+05:30`;

export const mockProvenance: Provenance = {
  gtfs_source: "synthetic",
  tickets_source: "synthetic",
  simulated: true,
  label: "SIMULATED demo fixtures (mock)",
  built_at: "2026-11-17T09:00:00+05:30",
};

export const mockOrigin: Place = {
  place_id: "place:MOCK_S01A",
  name: "Mock Terminal",
  stop_ids: ["MOCK_S01A", "MOCK_S01B"],
  lat: 28.63,
  lon: 77.2,
  routes: ["M1", "M2"],
};

export const mockDestination: Place = {
  place_id: "place:MOCK_S04A",
  name: "Mock Depot",
  stop_ids: ["MOCK_S04A"],
  lat: 28.66,
  lon: 77.25,
  routes: ["M1"],
};

const strongEvidence: Evidence = {
  quality: "medium",
  basis: "segment_period_daytype",
  ticket_count: 18,
  rider_count: 23,
  service_days: 5,
  scheduled_trips: 40,
  min_tickets_required: 10,
};

const pooledEvidence: Evidence = {
  quality: "low",
  basis: "segment_all_day",
  ticket_count: 12,
  rider_count: 14,
  service_days: 3,
  scheduled_trips: 96,
  min_tickets_required: 10,
};

const noEvidence: Evidence = {
  quality: "insufficient",
  basis: "none",
  ticket_count: 4,
  rider_count: 4,
  service_days: 1,
  scheduled_trips: 40,
  min_tickets_required: 10,
};

const segments: Segment[] = [
  {
    from_stop_id: "MOCK_S01A",
    to_stop_id: "MOCK_S02A",
    scheduled_departure: iso("08:10"),
    scheduled_arrival: iso("08:17"),
    scheduled_min: 7,
    crowding: { level: "higher", relative_rank: 0.87, evidence: strongEvidence },
  },
  {
    from_stop_id: "MOCK_S02A",
    to_stop_id: "MOCK_S03A",
    scheduled_departure: iso("08:17"),
    scheduled_arrival: iso("08:30"),
    scheduled_min: 13,
    crowding: { level: "lower", relative_rank: 0.24, evidence: pooledEvidence },
  },
  {
    from_stop_id: "MOCK_S03A",
    to_stop_id: "MOCK_S04A",
    scheduled_departure: iso("08:30"),
    scheduled_arrival: iso("08:46"),
    scheduled_min: 16,
    crowding: { level: "insufficient_evidence", relative_rank: null, evidence: noEvidence },
  },
];

export const mockBusLeg: BusLeg = {
  type: "bus",
  route: { route_id: "MOCK_R1", short_name: "M1", long_name: "Mock Terminal - Mock Depot" },
  trip_id: "MOCK_R1_0_wk_0810",
  headsign: "Mock Depot",
  direction_id: "0",
  board_stop: { stop_id: "MOCK_S01A", name: "Mock Terminal", lat: 28.63, lon: 77.2 },
  alight_stop: { stop_id: "MOCK_S04A", name: "Mock Depot", lat: 28.66, lon: 77.25 },
  scheduled_departure: iso("08:10"),
  scheduled_arrival: iso("08:46"),
  scheduled_min: 36,
  stops: [
    { stop_id: "MOCK_S01A", name: "Mock Terminal", lat: 28.63, lon: 77.2, sequence: 1, scheduled_arrival: iso("08:10"), scheduled_departure: iso("08:10") },
    { stop_id: "MOCK_S02A", name: "Mock Market", lat: 28.64, lon: 77.21, sequence: 2, scheduled_arrival: iso("08:17"), scheduled_departure: iso("08:17") },
    { stop_id: "MOCK_S03A", name: "Mock Ghat Road", lat: 28.65, lon: 77.23, sequence: 3, scheduled_arrival: iso("08:30"), scheduled_departure: iso("08:30") },
    { stop_id: "MOCK_S04A", name: "Mock Depot", lat: 28.66, lon: 77.25, sequence: 4, scheduled_arrival: iso("08:46"), scheduled_departure: iso("08:46") },
  ],
  segments,
};

export const mockFastestJourney: Journey = {
  journey_id: "MOCK_R1_0_wk_0810",
  scheduled_departure: iso("08:10"),
  scheduled_arrival: iso("08:46"),
  scheduled_travel_min: 36,
  initial_wait_min: 10,
  total_min: 46,
  transfers: 0,
  legs: [mockBusLeg],
  crowding: {
    level: "typical",
    relative_rank: 0.57,
    evidence_quality: "medium",
    coverage: 0.56,
    covered_min: 20,
    in_vehicle_min: 36,
    min_segment_ticket_count: 12,
    segment_counts: { lower: 1, typical: 0, higher: 1, insufficient_evidence: 1 },
  },
};

const mockTransfer: TransferLeg = {
  type: "transfer",
  from_stop: { stop_id: "MOCK_S02A", name: "Mock Market", lat: 28.64, lon: 77.21 },
  to_stop: { stop_id: "MOCK_S02B", name: "Mock Market", lat: 28.6401, lon: 77.2102 },
  scheduled_min: 6,
  walk_m: 40,
};

const secondBusLeg: BusLeg = {
  ...mockBusLeg,
  route: { route_id: "MOCK_R2", short_name: "M2", long_name: "Mock Market - Mock Depot" },
  trip_id: "MOCK_R2_0_wk_0823",
  board_stop: { stop_id: "MOCK_S02B", name: "Mock Market", lat: 28.6401, lon: 77.2102 },
  scheduled_departure: iso("08:23"),
  scheduled_arrival: iso("08:52"),
  scheduled_min: 29,
  stops: [
    { stop_id: "MOCK_S02B", name: "Mock Market", lat: 28.6401, lon: 77.2102, sequence: 1, scheduled_arrival: iso("08:23"), scheduled_departure: iso("08:23") },
    { stop_id: "MOCK_S04A", name: "Mock Depot", lat: 28.66, lon: 77.25, sequence: 2, scheduled_arrival: iso("08:52"), scheduled_departure: iso("08:52") },
  ],
  segments: [
    {
      from_stop_id: "MOCK_S02B",
      to_stop_id: "MOCK_S04A",
      scheduled_departure: iso("08:23"),
      scheduled_arrival: iso("08:52"),
      scheduled_min: 29,
      crowding: {
        level: "lower",
        relative_rank: 0.19,
        evidence: { ...strongEvidence, ticket_count: 31, rider_count: 36, service_days: 6 },
      },
    },
  ],
};

export const mockBalancedJourney: Journey = {
  journey_id: "MOCK_R1_0_wk_0810+MOCK_R2_0_wk_0823",
  scheduled_departure: iso("08:10"),
  scheduled_arrival: iso("08:52"),
  scheduled_travel_min: 42,
  initial_wait_min: 10,
  total_min: 52,
  transfers: 1,
  legs: [
    {
      ...mockBusLeg,
      alight_stop: { stop_id: "MOCK_S02A", name: "Mock Market", lat: 28.64, lon: 77.21 },
      scheduled_arrival: iso("08:17"),
      scheduled_min: 7,
      stops: mockBusLeg.stops.slice(0, 2),
      segments: segments.slice(0, 1),
    },
    mockTransfer,
    secondBusLeg,
  ],
  crowding: {
    level: "lower",
    relative_rank: 0.33,
    evidence_quality: "medium",
    coverage: 1,
    covered_min: 36,
    in_vehicle_min: 36,
    min_segment_ticket_count: 18,
    segment_counts: { lower: 1, typical: 0, higher: 1, insufficient_evidence: 0 },
  },
};

/** A response with all three option states the UI must handle: ok, ok and insufficient_evidence. */
export const mockJourneyResponse: JourneyResponse = {
  request: {
    origin: mockOrigin,
    destination: mockDestination,
    date: DAY,
    time: "08:00",
    day_type: "weekday",
    period: "am_peak",
  },
  status: "ok",
  message: "3 options from 14 scheduled journeys.",
  candidates_considered: 14,
  options: [
    {
      kind: "fastest",
      label: "Fastest",
      status: "ok",
      journey: mockFastestJourney,
      reason: {
        summary: "Earliest scheduled arrival (08:46) of 14 journeys departing within 60 min.",
        details: ["Direct on route M1.", "Scheduled travel time 36 min after a 10 min wait."],
        metrics: { total_min: 46, minutes_slower_than_fastest: 0 },
      },
      same_journey_as: null,
    },
    {
      kind: "balanced",
      label: "Balanced",
      status: "ok",
      journey: mockBalancedJourney,
      reason: {
        summary: "Best trade-off of scheduled time and relative crowding among 6 journeys with enough evidence.",
        details: ["6 min slower than Fastest.", "One change at Mock Market."],
        metrics: { total_min: 52, minutes_slower_than_fastest: 6 },
      },
      same_journey_as: null,
    },
    {
      kind: "less_crowded",
      label: "Less crowded",
      status: "insufficient_evidence",
      journey: null,
      reason: {
        summary: "No journey has ticket evidence on at least 60% of its scheduled minutes.",
        details: ["14 scheduled journeys were considered.", "Use Fastest, which relies on the timetable only."],
        metrics: { candidates: 14, candidates_with_evidence: 0 },
      },
      same_journey_as: null,
    },
  ],
  provenance: mockProvenance,
  disclaimers: [
    "Times are scheduled times from static GTFS. They are not live arrivals.",
    "Relative crowding is estimated from ticket samples. Ticket samples are not verified occupancy: this is not a seat count and not a percentage full.",
  ],
  road_traffic: {
    status: "not_configured",
    note: "No road-traffic provider is configured. No calls are made to Google.",
  },
};

export const mockNoJourneyResponse: JourneyResponse = {
  ...mockJourneyResponse,
  status: "no_journey",
  message: "No scheduled journey departs within 60 min of 23:50.",
  candidates_considered: 0,
  options: mockJourneyResponse.options.map((option) => ({
    ...option,
    status: "no_journey" as const,
    journey: null,
    reason: { summary: "No scheduled journey in the search window.", details: [], metrics: {} },
  })),
};

export const mockMeta: MetaResponse = {
  provenance: mockProvenance,
  counts: { stops: 8, places: 4, routes: 2, trips: 120, patterns: 4 },
  service_date_range: { start: "2026-01-01", end: "2027-12-31" },
  suggested_query: { date: DAY, time: "08:00" },
  periods: [{ id: "am_peak", label: "Morning peak", start: "07:00", end: "11:00" }],
  day_types: ["weekday", "weekend"],
  settings: {},
  fallbacks: [
    { basis: "segment_period_daytype", description: "Exact segment, period and day type.", quality_cap: "high" },
    { basis: "segment_period", description: "Same segment and period, both day types pooled.", quality_cap: "medium" },
  ],
  disclaimers: mockJourneyResponse.disclaimers,
  road_traffic: mockJourneyResponse.road_traffic,
};

export const mockDataQuality: DataQualityReport = {
  generated_at: "2026-11-17T09:00:00+05:30",
  provenance: mockProvenance,
  gtfs: {
    summary: { errors: 0, warnings: 1, infos: 2 },
    issues: [
      { code: "duplicate_stop_name", severity: "warning", file: "stops.txt", count: 4, message: "Stops share a name.", samples: [] },
    ],
  },
  tickets: {
    summary: { errors: 2, warnings: 0, infos: 0 },
    issues: [
      { code: "bad_timestamp", severity: "error", file: "tickets.csv", count: 2, message: "Timestamp could not be parsed.", samples: [] },
    ],
  },
  matching: { total: 200, by_status: { matched: 185, ambiguous_stop: 9, unmatched_route: 6 }, match_rate: 0.925 },
  crowding: {},
  blocked: ["Real GTFS feed: download needs a registered account."],
};
