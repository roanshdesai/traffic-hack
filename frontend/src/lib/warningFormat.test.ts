import { describe, expect, it } from "vitest";
import type { Site, WindowAssessment } from "../api/warningTypes";
import { addMinutes, clampStamp, metricText, ratioText, readingText, replayBounds, snapStamp, warningWhen } from "./warningFormat";

const site: Site = {
  site_id: "MOCK",
  name: "Mock",
  kind: "bus_stop",
  lat: null,
  lon: null,
  source: "ticket_sample",
  coverage: "sample",
  window_minutes: 60,
  unit: "e-ticket boardings",
  alert_threshold: null,
};

const base: WindowAssessment = {
  window_start: "2026-10-28T09:00",
  window_end: "2026-10-28T10:00",
  observed: 41,
  baseline: { median: 12.4, low: 8, high: 16, support_days: 10, basis: "site_daytype_slot", quality: "medium" },
  ratio: 3.3,
  z: 5,
  status: "overcrowding_alert",
  triggers: ["relative"],
  reasons: [],
};

describe("warningFormat", () => {
  it("does time arithmetic on wall-clock strings, across midnight", () => {
    expect(addMinutes("2026-11-18T23:45", 15)).toBe("2026-11-19T00:00");
    expect(addMinutes("2026-11-19T00:00", -15)).toBe("2026-11-18T23:45");
    expect(snapStamp("2026-11-18T17:52")).toBe("2026-11-18T17:45");
  });

  it("clamps to the replay period", () => {
    const bounds = replayBounds({ start: "2026-11-16", end: "2026-11-22" });
    expect(clampStamp("2026-11-01T08:00", bounds)).toBe("2026-11-16T00:00");
    expect(clampStamp("2026-12-01T08:00", bounds)).toBe("2026-11-22T23:45");
    expect(clampStamp("2026-11-18T08:00", bounds)).toBe("2026-11-18T08:00");
  });

  it("builds readings only from API numbers, in the site's unit", () => {
    expect(readingText(site, base)).toBe("41 e-ticket boardings vs usually 12");
    expect(readingText(site, { ...base, baseline: null })).toBe("41 e-ticket boardings (no usual level for this time yet)");
    expect(readingText(site, { ...base, observed: null })).toBe("No usable reading for this window");
    expect(ratioText(1.92)).toBe("1.9× usual");
    expect(warningWhen("2026-11-18T18:15", 30)).toBe("around 18:15 (in 30 min)");
  });

  it("formats metrics without inventing precision", () => {
    expect(metricText(0.8123456)).toBe("0.812");
    expect(metricText(4)).toBe("4");
    expect(metricText(null)).toBe("n/a");
    expect(metricText(true)).toBe("yes");
  });
});
