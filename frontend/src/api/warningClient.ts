/** Client for the overcrowding early warning (the main product). Contract: docs/API.md. */
import { getJson } from "./client";
import type {
  AlertsResponse,
  EvaluationResponse,
  OverviewResponse,
  SiteListResponse,
  TimelineResponse,
  WarningDataQualityReport,
  WarningMeta,
} from "./warningTypes";

export function fetchWarningMeta(signal?: AbortSignal): Promise<WarningMeta> {
  return getJson<WarningMeta>("/api/meta", undefined, signal);
}

/** `at` is a replay time, `YYYY-MM-DDTHH:MM`. Omit it to use the server's default. */
export function fetchOverview(at?: string, signal?: AbortSignal): Promise<OverviewResponse> {
  return getJson<OverviewResponse>("/api/overview", at ? { at } : undefined, signal);
}

export function searchSites(q: string, limit = 20, signal?: AbortSignal): Promise<SiteListResponse> {
  return getJson<SiteListResponse>("/api/sites", { q, limit: String(limit) }, signal);
}

export function fetchTimeline(siteId: string, date?: string, signal?: AbortSignal): Promise<TimelineResponse> {
  return getJson<TimelineResponse>(
    `/api/sites/${encodeURIComponent(siteId)}/timeline`,
    date ? { date } : undefined,
    signal,
  );
}

export function fetchAlerts(date?: string, signal?: AbortSignal): Promise<AlertsResponse> {
  return getJson<AlertsResponse>("/api/alerts", date ? { date } : undefined, signal);
}

export function fetchEvaluation(signal?: AbortSignal): Promise<EvaluationResponse> {
  return getJson<EvaluationResponse>("/api/evaluation", undefined, signal);
}

export function fetchWarningDataQuality(signal?: AbortSignal): Promise<WarningDataQualityReport> {
  return getJson<WarningDataQualityReport>("/api/data-quality", undefined, signal);
}
