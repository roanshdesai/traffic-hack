import { describe, expect, it, vi } from "vitest";
import { formatClock, formatDistance, formatMinutes, humanize, nowInDelhi, supportText } from "./format";

describe("formatClock", () => {
  it("slices HH:MM out of an ISO time with the +05:30 offset", () => {
    expect(formatClock("2026-11-16T08:12:00+05:30")).toBe("08:12");
    expect(formatClock("2026-11-16T23:59:00+05:30")).toBe("23:59");
    expect(formatClock("2026-11-17T00:05:00+05:30")).toBe("00:05");
  });

  it("does not depend on the machine time zone", () => {
    try {
      for (const tz of ["UTC", "America/Los_Angeles", "Pacific/Kiritimati"]) {
        vi.stubEnv("TZ", tz);
        expect(formatClock("2026-11-16T00:30:00+05:30")).toBe("00:30");
      }
      // Sanity check that the zone really changed: Date-based formatting would give 19:00 here.
      vi.stubEnv("TZ", "UTC");
      expect(new Date("2026-11-16T00:30:00+05:30").getHours()).toBe(19);
    } finally {
      vi.unstubAllEnvs();
    }
  });

  it("accepts a bare HH:MM and passes through anything else", () => {
    expect(formatClock("08:00")).toBe("08:00");
    expect(formatClock("soon")).toBe("soon");
  });
});

describe("formatMinutes", () => {
  it("formats minutes and hours", () => {
    expect(formatMinutes(0)).toBe("0 min");
    expect(formatMinutes(36)).toBe("36 min");
    expect(formatMinutes(36.4)).toBe("36 min");
    expect(formatMinutes(60)).toBe("1 h");
    expect(formatMinutes(65)).toBe("1 h 05 min");
  });
});

describe("other helpers", () => {
  it("writes support counts with correct plurals", () => {
    expect(supportText(18, 5)).toBe("18 tickets over 5 days");
    expect(supportText(1, 1)).toBe("1 ticket over 1 day");
    expect(supportText(0, 0)).toBe("0 tickets over 0 days");
  });

  it("rounds walking distance", () => {
    expect(formatDistance(40)).toBe("~40 m");
    expect(formatDistance(183)).toBe("~200 m");
  });

  it("humanizes status codes", () => {
    expect(humanize("ambiguous_stop")).toBe("Ambiguous stop");
  });

  it("returns the Delhi wall-clock date and time", () => {
    // 2026-11-16 20:00 UTC is 2026-11-17 01:30 in Asia/Kolkata.
    expect(nowInDelhi(new Date("2026-11-16T20:00:00Z"))).toEqual({ date: "2026-11-17", time: "01:30" });
  });
});
