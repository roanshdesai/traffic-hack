import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import App from "./App";
import { DataQualityPanel } from "./components/DataQualityPanel";
import { SimulatedBanner, WARNING_SIMULATED_TEXT } from "./components/SimulatedBanner";
import { fetchTimeline } from "./api/warningClient";
import { mockMeta } from "./test/fixtures";
import {
  mockAlerts,
  mockEvaluation,
  mockOverview,
  mockTimeline,
  mockWarningDataQuality,
  mockWarningMeta,
  mockWarningProvenance,
} from "./test/warningFixtures";

function jsonResponse(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), { status, headers: { "Content-Type": "application/json" } });
}

/** Routes mock API calls by path. All data is MOCK data from src/test/warningFixtures.ts. */
function stubApi(overrides: Record<string, () => Response> = {}) {
  const calls: string[] = [];
  const handler = vi.fn(async (input: RequestInfo | URL) => {
    const url = new URL(String(input), "http://localhost");
    calls.push(url.pathname + url.search);
    const override = overrides[url.pathname];
    if (override) return override();
    switch (url.pathname) {
      case "/api/meta":
        return jsonResponse(mockWarningMeta);
      case "/api/overview":
        return jsonResponse({ ...mockOverview, at: url.searchParams.get("at") ?? mockOverview.at });
      case "/api/sites/MOCK_SITE_04/timeline":
        return jsonResponse(mockTimeline);
      case "/api/alerts":
        return jsonResponse(mockAlerts);
      case "/api/evaluation":
        return jsonResponse(mockEvaluation);
      case "/api/data-quality":
        return jsonResponse(mockWarningDataQuality);
      case "/api/planner/meta":
        return jsonResponse(mockMeta);
      default:
        return jsonResponse({ detail: "Not found" }, 404);
    }
  });
  vi.stubGlobal("fetch", handler);
  return calls;
}

/** Words the monitor must never show. Negated uses ("not live", "not verified") are allowed. */
function forbiddenWords(text: string): string[] {
  const cleaned = text.replace(/\bnot (a )?(live|verified)\b/gi, "");
  const patterns = [/\blive\b/i, /real-time/i, /\bverified\b/i, /% full/i, /\bseats?\b/i];
  return patterns.filter((p) => p.test(cleaned)).map(String);
}

function openDetails(summaryText: RegExp) {
  const summary = screen.getByText(summaryText, { selector: "summary" });
  const details = summary.closest("details")!;
  details.open = true;
  fireEvent(details, new Event("toggle"));
}

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("Overcrowding monitor (main view)", () => {
  it("is the default view, with the replay note and the simulated banner", async () => {
    stubApi();
    render(<App />);
    expect(screen.getByRole("heading", { level: 1 }).textContent).toBe("Overcrowding Early Warning (prototype)");
    expect(screen.getByText("Replay of recorded data, not live.")).toBeTruthy();
    const banner = await screen.findByRole("note", { name: /simulated data/i });
    expect(banner.textContent).toContain(WARNING_SIMULATED_TEXT);
    expect(screen.getByRole("button", { name: "Overcrowding monitor" }).getAttribute("aria-current")).toBe("page");
  });

  it("asks for the overview at the default replay time and lists sites in API order", async () => {
    const calls = stubApi();
    render(<App />);
    const cards = await screen.findAllByTestId("site-card");
    expect(cards.map((c) => c.querySelector(".site-card__name")!.textContent)).toEqual([
      "Mock Stadium Stop",
      "Mock Interchange Stop",
      "Mock New Stop",
      "Mock College Stop",
    ]);
    expect(calls).toContain("/api/overview?at=2026-11-18T17%3A45");
    expect(cards[0].textContent).toContain("Overcrowding alert");
    expect(cards[0].textContent).toContain("182 people counted vs usually 95");
    expect(cards[0].textContent).toContain("1.9× usual");
    expect(cards[1].textContent).toContain("Usual for this time");
    expect(cards[2].textContent).toContain("Not enough history");
    expect(cards[2].textContent).toContain("E-ticket sample");
    expect(cards[3].textContent).toContain("No data");
    expect(cards[3].textContent).toContain("No usable reading for this window");
  });

  it("shows the early warning line", async () => {
    stubApi();
    render(<App />);
    const cards = await screen.findAllByTestId("site-card");
    expect(cards[1].textContent).toContain("Early warning");
    expect(cards[1].textContent).toContain("around 18:15 (in 30 min)");
    expect(screen.getByTestId("chip-early_warning").textContent).toContain("1");
  });

  it("does not style unknown states like usual ones", async () => {
    stubApi();
    render(<App />);
    const cards = await screen.findAllByTestId("site-card");
    expect(cards[2].querySelector('[data-status="insufficient_evidence"]')!.className).toContain(
      "status--insufficient_evidence",
    );
    expect(cards[3].querySelector('[data-status="no_data"]')!.className).not.toContain("status--normal");
  });

  it("steps the replay time by 15 minutes", async () => {
    const calls = stubApi();
    render(<App />);
    await screen.findAllByTestId("site-card");
    fireEvent.click(screen.getByRole("button", { name: "+15 min" }));
    await waitFor(() => expect(calls).toContain("/api/overview?at=2026-11-18T18%3A00"));
    expect((screen.getByLabelText("Time") as HTMLInputElement).value).toBe("18:00");
  });

  it("filters to alerts and warnings only", async () => {
    stubApi();
    render(<App />);
    await screen.findAllByTestId("site-card");
    fireEvent.click(screen.getByLabelText("Only show alerts and warnings"));
    expect(screen.getAllByTestId("site-card")).toHaveLength(2);
  });

  it("opens a site with its forecast table, SVG chart, simulated event and episodes", async () => {
    stubApi();
    render(<App />);
    const cards = await screen.findAllByTestId("site-card");
    fireEvent.click(cards[0]);
    expect(await screen.findByTestId("timeline-chart")).toBeTruthy();
    const table = screen.getByTestId("forecast-table");
    expect(screen.getByRole("heading", { name: "Forecast (estimate)" })).toBeTruthy();
    expect(within(table).getAllByRole("row")).toHaveLength(3);
    expect(table.textContent).toContain("171 (150–193)");
    const chart = screen.getByTestId("timeline-chart");
    expect(chart.tagName.toLowerCase()).toBe("svg");
    expect(chart.textContent).toContain("Simulated test event");
    expect(chart.textContent).toContain("after replay time");
    expect(screen.getByText(/operator-set threshold of 150 \(a setting, not a verified capacity\)/)).toBeTruthy();
    expect(screen.getByText("First forecast at 17:15 (30 min ahead)")).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "← All sites" }));
    expect(await screen.findAllByTestId("site-card")).toHaveLength(4);
  });

  it("hides simulated events when the data is not simulated", async () => {
    const real = { ...mockWarningProvenance, simulated: false, origin: "real" as const };
    stubApi({
      "/api/meta": () => jsonResponse({ ...mockWarningMeta, provenance: real }),
      "/api/overview": () => jsonResponse({ ...mockOverview, provenance: real }),
      "/api/sites/MOCK_SITE_04/timeline": () => jsonResponse({ ...mockTimeline, provenance: real }),
    });
    render(<App />);
    const cards = await screen.findAllByTestId("site-card");
    expect(screen.queryByRole("note", { name: /simulated data/i })).toBeNull();
    fireEvent.click(cards[0]);
    const chart = await screen.findByTestId("timeline-chart");
    expect(chart.textContent).not.toContain("Simulated test event");
  });

  it("lists the day's alert episodes with their match against simulated events", async () => {
    const calls = stubApi();
    render(<App />);
    await screen.findAllByTestId("site-card");
    fireEvent.click(screen.getByRole("button", { name: "Alerts this day" }));
    const episodes = await screen.findAllByTestId("alert-episode");
    expect(calls).toContain("/api/alerts?date=2026-11-18");
    expect(episodes[0].textContent).toContain("Matches a simulated test event");
    expect(episodes[1].textContent).toContain("a false alarm on test data");
    expect(episodes[1].textContent).toContain("Not forecast in advance");
  });

  it("shows evaluation and the warning data-quality report", async () => {
    stubApi();
    render(<App />);
    await screen.findAllByTestId("site-card");
    openDetails(/How well does this work\?/);
    const evaluation = await screen.findByTestId("evaluation");
    expect(evaluation.textContent).toContain("How well this works on test data");
    expect(evaluation.textContent).toContain("Measured on SIMULATED events");
    openDetails(/Data quality/);
    const report = await screen.findByTestId("dq-report");
    expect(report.textContent).toContain("simulated_camera_counts.csv");
    expect(report.textContent).toContain("6 errors");
    expect(report.textContent).toContain("Mock: real camera feed not connected.");
  });

  it("keeps road traffic in its own box, outside every status card", async () => {
    stubApi();
    render(<App />);
    await screen.findAllByTestId("site-card");
    const road = screen.getByTestId("road-traffic");
    expect(road.textContent).toContain("Not connected");
    expect(road.closest(".site-card, .detail")).toBeNull();
  });

  it("never shows live, real-time, verified, seats or % full", async () => {
    stubApi();
    render(<App />);
    const cards = await screen.findAllByTestId("site-card");
    openDetails(/How well does this work\?/);
    await screen.findByTestId("evaluation");
    expect(forbiddenWords(document.body.textContent ?? "")).toEqual([]);
    fireEvent.click(cards[0]);
    await screen.findByTestId("timeline-chart");
    expect(forbiddenWords(document.body.textContent ?? "")).toEqual([]);
    fireEvent.click(screen.getByRole("button", { name: "← All sites" }));
    fireEvent.click(await screen.findByRole("button", { name: "Alerts this day" }));
    await screen.findAllByTestId("alert-episode");
    expect(forbiddenWords(document.body.textContent ?? "")).toEqual([]);
  });

  it("explains how to load data when the API has no dataset", async () => {
    stubApi({
      "/api/meta": () => jsonResponse({ detail: { code: "no_dataset", message: "No dataset." } }, 503),
    });
    render(<App />);
    expect((await screen.findByTestId("error-state")).textContent).toContain("make data");
  });

  it("switches to the secondary journey planner, which uses /api/planner", async () => {
    const calls = stubApi();
    render(<App />);
    await screen.findAllByTestId("site-card");
    fireEvent.click(screen.getByRole("button", { name: "Journey planner (secondary)" }));
    expect(await screen.findByRole("heading", { name: "Journey planner (secondary)" })).toBeTruthy();
    await waitFor(() => expect(calls).toContain("/api/planner/meta"));
    expect(screen.queryAllByTestId("site-card")).toHaveLength(0);
  });
});

describe("shared components", () => {
  it("SimulatedBanner takes custom text", () => {
    render(<SimulatedBanner provenance={{ simulated: true }} text="Custom simulated text" />);
    expect(screen.getByRole("note").textContent).toContain("Custom simulated text");
  });

  it("DataQualityPanel renders a warning report from an injected loader", async () => {
    const { container } = render(<DataQualityPanel load={async () => mockWarningDataQuality} />);
    const details = container.querySelector("details")!;
    details.open = true;
    fireEvent(details, new Event("toggle"));
    const report = await screen.findByTestId("dq-report");
    expect(report.textContent).toContain("Baseline cells");
  });

  it("warning client encodes the site id in the timeline path", async () => {
    const calls = stubApi();
    await fetchTimeline("MOCK_SITE_04", "2026-11-18");
    expect(calls).toEqual(["/api/sites/MOCK_SITE_04/timeline?date=2026-11-18"]);
    await fetchTimeline("stop:A B/C").catch(() => undefined);
    expect(calls[1]).toBe("/api/sites/stop%3AA%20B%2FC/timeline");
  });
});
