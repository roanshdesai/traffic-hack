import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { PlannerView } from "./PlannerView";
import { DataQualityPanel } from "../components/DataQualityPanel";
import { ErrorState } from "../components/ErrorState";
import { SimulatedBanner } from "../components/SimulatedBanner";
import { ApiError } from "../api/client";
import { mockDataQuality, mockJourneyResponse, mockMeta, mockOrigin, mockDestination, mockProvenance } from "../test/fixtures";

function jsonResponse(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), { status, headers: { "Content-Type": "application/json" } });
}

/** Routes mock API calls by path. All data is mock data from src/test/fixtures.ts. */
function stubApi(overrides: Record<string, () => Response> = {}) {
  const calls: string[] = [];
  const handler = vi.fn(async (input: RequestInfo | URL) => {
    const url = new URL(String(input), "http://localhost");
    calls.push(url.pathname + url.search);
    const override = overrides[url.pathname];
    if (override) return override();
    if (url.pathname === "/api/planner/meta") return jsonResponse(mockMeta);
    if (url.pathname === "/api/planner/stops") {
      const q = (url.searchParams.get("q") ?? "").toLowerCase();
      const places = [mockOrigin, mockDestination].filter((p) => p.name.toLowerCase().includes(q));
      return jsonResponse({ query: q, places });
    }
    if (url.pathname === "/api/planner/journeys") return jsonResponse(mockJourneyResponse);
    if (url.pathname === "/api/planner/data-quality") return jsonResponse(mockDataQuality);
    return jsonResponse({ detail: "Not found" }, 404);
  });
  vi.stubGlobal("fetch", handler);
  return calls;
}

describe("SimulatedBanner", () => {
  it("appears when provenance.simulated is true", () => {
    render(<SimulatedBanner provenance={mockProvenance} />);
    expect(screen.getByRole("note", { name: /simulated data/i }).textContent).toContain("Simulated data");
  });

  it("is absent when the data is not simulated", () => {
    render(<SimulatedBanner provenance={{ ...mockProvenance, simulated: false }} />);
    expect(screen.queryByRole("note", { name: /simulated data/i })).toBeNull();
  });
});

describe("ErrorState", () => {
  it("tells the user to run make data when no dataset is loaded", () => {
    render(<ErrorState error={new ApiError(503, { code: "no_dataset", message: "No processed dataset." })} />);
    expect(screen.getByTestId("error-state").textContent).toContain("make data");
  });

  it("shows the API message for other errors", () => {
    render(<ErrorState error={new ApiError(404, { code: "unknown_place", message: "Unknown place: x" })} />);
    expect(screen.getByTestId("error-state").textContent).toContain("Unknown place: x");
  });
});

describe("DataQualityPanel", () => {
  it("summarises the report", async () => {
    const { container } = render(<DataQualityPanel load={async () => mockDataQuality} />);
    const details = container.querySelector("details")!;
    details.open = true;
    fireEvent(details, new Event("toggle"));
    const report = await screen.findByTestId("dq-report");
    expect(report.textContent).toContain("0 errors");
    expect(report.textContent).toContain("1 warnings");
    expect(report.textContent).toContain("duplicate_stop_name");
    expect(report.textContent).toContain("Ambiguous stop");
    expect(report.textContent).toContain("92.5% of ticket records matched");
    expect(report.textContent).toContain("Real GTFS feed: download needs a registered account.");
  });
});

describe("PlannerView (secondary)", () => {
  beforeEach(() => {
    vi.useRealTimers();
  });

  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("calls only /api/planner paths", async () => {
    const calls = stubApi();
    render(<PlannerView />);
    await screen.findByLabelText("From");
    expect(calls.length).toBeGreaterThan(0);
    expect(calls.every((c) => c.startsWith("/api/planner/"))).toBe(true);
  });

  it("shows the simulated banner from /api/planner/meta and uses the suggested date and time", async () => {
    stubApi();
    render(<PlannerView />);
    expect(await screen.findByRole("note", { name: /simulated data/i })).toBeTruthy();
    expect((screen.getByLabelText("Date") as HTMLInputElement).value).toBe("2026-11-16");
    expect((screen.getByLabelText("Leave after") as HTMLInputElement).value).toBe("08:00");
    expect(screen.getByTestId("road-traffic").textContent).toContain("Not connected");
  });

  it("searches with place ids and renders the three options", async () => {
    const calls = stubApi();
    render(<PlannerView />);

    const from = await screen.findByLabelText("From");
    fireEvent.focus(from);
    fireEvent.change(from, { target: { value: "Terminal" } });
    fireEvent.click(await screen.findByRole("option", { name: /Mock Terminal/ }));

    const to = screen.getByLabelText("To");
    fireEvent.focus(to);
    fireEvent.change(to, { target: { value: "Depot" } });
    fireEvent.click(await screen.findByRole("option", { name: /Mock Depot/ }));

    fireEvent.click(screen.getByRole("button", { name: "Compare journeys" }));

    await waitFor(() => expect(screen.getAllByRole("tab")).toHaveLength(3));
    const journeyCall = calls.find((c) => c.startsWith("/api/planner/journeys"))!;
    const params = new URL(journeyCall, "http://localhost").searchParams;
    expect(params.get("from")).toBe("place:MOCK_S01A");
    expect(params.get("to")).toBe("place:MOCK_S04A");
    expect(params.get("date")).toBe("2026-11-16");
    expect(params.get("time")).toBe("08:00");
    expect(screen.getByRole("note", { name: /simulated data/i })).toBeTruthy();
  });

  it("asks for both places before searching", async () => {
    const calls = stubApi();
    render(<PlannerView />);
    fireEvent.click(await screen.findByRole("button", { name: "Compare journeys" }));
    expect(screen.getByText("Choose a starting stop from the list.")).toBeTruthy();
    expect(calls.some((c) => c.startsWith("/api/planner/journeys"))).toBe(false);
  });

  it("explains how to load data when the API has no dataset", async () => {
    stubApi({
      "/api/planner/meta": () => jsonResponse({ detail: { code: "no_dataset", message: "No processed dataset is loaded." } }, 503),
    });
    render(<PlannerView />);
    const error = await screen.findByTestId("error-state");
    expect(error.textContent).toContain("make data");
  });
});
