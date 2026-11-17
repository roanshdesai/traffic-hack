/**
 * Client for the secondary journey planner (`/api/planner/*`, see docs/API-planner.md).
 * The main early-warning client is `warningClient.ts`.
 */
import type {
  DataQualityReport,
  ErrorDetail,
  JourneyResponse,
  MetaResponse,
  StopSearchResponse,
} from "./types";

const API_BASE: string = (import.meta.env.VITE_API_BASE ?? "").replace(/\/$/, "");

/** An error returned by the API as `{"detail": {"code", "message"}}`, or a transport failure. */
export class ApiError extends Error {
  readonly code: string;
  readonly status: number;

  constructor(status: number, detail: ErrorDetail) {
    super(detail.message);
    this.name = "ApiError";
    this.status = status;
    this.code = detail.code;
  }
}

function parseErrorDetail(status: number, body: unknown): ErrorDetail {
  const detail = (body as { detail?: unknown } | null)?.detail;
  if (detail && typeof detail === "object" && !Array.isArray(detail)) {
    const d = detail as Partial<ErrorDetail>;
    if (typeof d.code === "string" && typeof d.message === "string") {
      return { code: d.code, message: d.message };
    }
  }
  if (typeof detail === "string") {
    return { code: `http_${status}`, message: detail };
  }
  if (Array.isArray(detail)) {
    // FastAPI request-validation errors (HTTP 422).
    return { code: "validation_error", message: "The request was not valid. Check the search fields." };
  }
  return { code: `http_${status}`, message: `The server answered with HTTP ${status}.` };
}

/** GET a JSON endpoint; errors become `ApiError`. Shared by the planner and warning clients. */
export async function getJson<T>(path: string, params?: Record<string, string>, signal?: AbortSignal): Promise<T> {
  const query = params ? `?${new URLSearchParams(params).toString()}` : "";
  let response: Response;
  try {
    response = await fetch(`${API_BASE}${path}${query}`, {
      headers: { Accept: "application/json" },
      signal,
    });
  } catch (err) {
    if (err instanceof DOMException && err.name === "AbortError") throw err;
    throw new ApiError(0, {
      code: "network_error",
      message: "Could not reach the API. Is the backend running?",
    });
  }

  let body: unknown = null;
  try {
    body = await response.json();
  } catch {
    body = null;
  }

  if (!response.ok) {
    throw new ApiError(response.status, parseErrorDetail(response.status, body));
  }
  if (body === null) {
    throw new ApiError(response.status, { code: "bad_response", message: "The API did not return JSON." });
  }
  return body as T;
}

export function fetchMeta(signal?: AbortSignal): Promise<MetaResponse> {
  return getJson<MetaResponse>("/api/planner/meta", undefined, signal);
}

export function searchStops(q: string, limit = 8, signal?: AbortSignal): Promise<StopSearchResponse> {
  return getJson<StopSearchResponse>("/api/planner/stops", { q, limit: String(limit) }, signal);
}

export interface JourneyQuery {
  /** `place_id` (or a single `stop_id`). */
  from: string;
  to: string;
  /** YYYY-MM-DD */
  date: string;
  /** HH:MM, depart-after. */
  time: string;
}

export function fetchJourneys(query: JourneyQuery, signal?: AbortSignal): Promise<JourneyResponse> {
  return getJson<JourneyResponse>(
    "/api/planner/journeys",
    { from: query.from, to: query.to, date: query.date, time: query.time },
    signal,
  );
}

export function fetchDataQuality(signal?: AbortSignal): Promise<DataQualityReport> {
  return getJson<DataQualityReport>("/api/planner/data-quality", undefined, signal);
}
