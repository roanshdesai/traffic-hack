import { fireEvent, render, screen, within } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { mockJourneyResponse, mockNoJourneyResponse } from "../test/fixtures";
import { Results } from "./Results";

/** Words the UI must never use: ticket samples are not occupancy, and times are not live. */
const FORBIDDEN = [/\bseats?\b/i, /% full/i, /percent full/i, /\bavailable\b/i, /\boccupancy\b/i];

describe("Results", () => {
  it("always renders the three options in order", () => {
    render(<Results response={mockJourneyResponse} />);
    const tabs = screen.getAllByRole("tab");
    expect(tabs.map((tab) => within(tab).getByText(/Fastest|Balanced|Less crowded/).textContent)).toEqual([
      "Fastest",
      "Balanced",
      "Less crowded",
    ]);
    expect(tabs[0].getAttribute("aria-selected")).toBe("true");
    expect(tabs[0].textContent).toContain("46 min");
    expect(tabs[2].textContent).toContain("Not enough evidence");
  });

  it("shows the Fastest journey with scheduled times, reason and ordered stops", () => {
    render(<Results response={mockJourneyResponse} />);
    const card = screen.getByTestId("journey-card");
    expect(card.textContent).toContain("08:10");
    expect(card.textContent).toContain("08:46");
    expect(card.textContent).toMatch(/scheduled/i);
    expect(card.textContent).toContain("Earliest scheduled arrival (08:46)");
    expect(card.textContent).toContain("Evidence for 20 of 36 scheduled min");
    expect(card.textContent).toContain("Evidence: medium");

    const stops = within(card).getAllByTestId("stop");
    expect(stops.map((stop) => stop.textContent)).toEqual([
      "08:10Mock Terminal · board",
      "08:17Mock Market",
      "08:30Mock Ghat Road",
      "08:46Mock Depot · get off",
    ]);
  });

  it("renders segment-level relative crowding with support counts and basis", () => {
    render(<Results response={mockJourneyResponse} />);
    const segments = screen.getAllByTestId("segment");
    expect(segments).toHaveLength(3);

    expect(segments[0].textContent).toContain("Relatively more crowded");
    expect(segments[0].textContent).toContain("18 tickets over 5 days");
    expect(segments[0].textContent).toContain("this segment, this period and day type");

    expect(segments[1].textContent).toContain("Relatively less crowded");
    expect(segments[1].textContent).toContain("12 tickets over 3 days");
    expect(segments[1].textContent).toContain("pooled across the whole day");

    expect(segments[2].getAttribute("data-level")).toBe("insufficient_evidence");
    expect(segments[2].textContent).toContain("Not enough evidence");
    expect(segments[2].textContent).toContain("4 tickets over 1 day");
    expect(segments[2].textContent).toContain("no usable samples");
    expect(segments[2].textContent).not.toContain("Relatively less crowded");
  });

  it("shows the explicit insufficient-evidence state, with no journey, for that option", () => {
    render(<Results response={mockJourneyResponse} />);
    fireEvent.click(screen.getByRole("tab", { name: /Less crowded/ }));

    const state = screen.getByTestId("insufficient-evidence");
    expect(state.textContent).toContain("Insufficient evidence");
    expect(state.textContent).toContain("No journey has ticket evidence on at least 60% of its scheduled minutes.");
    expect(state.textContent).toContain("It does not mean these buses are less crowded.");
    expect(screen.queryByTestId("journey-card")).toBeNull();
    expect(screen.queryAllByTestId("segment")).toHaveLength(0);

    // The state can send the user to Fastest, which needs only the timetable.
    fireEvent.click(within(state).getByRole("button", { name: /Fastest/ }));
    expect(screen.getByTestId("journey-card")).toBeTruthy();
    expect(screen.getByRole("tab", { name: /Fastest/ }).getAttribute("aria-selected")).toBe("true");
  });

  it("shows transfers on a journey with a change", () => {
    render(<Results response={mockJourneyResponse} />);
    fireEvent.click(screen.getByRole("tab", { name: /Balanced/ }));
    const transfer = screen.getByTestId("transfer");
    expect(transfer.textContent).toContain("Change at Mock Market, scheduled gap 6 min, ~40 m walk");
    expect(screen.getByTestId("journey-card").textContent).toContain("1 change");
  });

  it("never shows relative_rank as a percentage and never claims seats or occupancy", () => {
    const { container } = render(<Results response={mockJourneyResponse} />);
    for (const kind of [/Fastest/, /Balanced/]) {
      fireEvent.click(screen.getByRole("tab", { name: kind }));
      const text = screen.getByTestId("journey-card").textContent ?? "";
      expect(text).not.toContain("%");
      // Mock ranks are 0.87, 0.24, 0.57, 0.19 and 0.33: neither the raw rank nor a x100 form may appear.
      expect(text).not.toMatch(/\b0\.\d/);
      for (const scaled of ["87", "24", "57", "19", "33"]) {
        expect(text).not.toContain(scaled);
      }
      for (const pattern of FORBIDDEN) {
        expect(text).not.toMatch(pattern);
      }
    }
    expect(container.textContent).not.toMatch(/\blive arrival/i);
  });

  it("shows the same-journey note when an option repeats an earlier one", () => {
    const response = structuredClone(mockJourneyResponse);
    response.options[1] = { ...response.options[0], kind: "balanced", label: "Balanced", same_journey_as: "fastest" };
    render(<Results response={response} />);
    fireEvent.click(screen.getByRole("tab", { name: /Balanced/ }));
    expect(screen.getByTestId("same-as").textContent).toBe("Same journey as Fastest.");
  });

  it("labels the requested period from the meta period list when given", () => {
    render(
      <Results
        response={mockJourneyResponse}
        periods={[{ id: "am_peak", label: "Morning peak", start: "07:00", end: "11:00" }]}
      />,
    );
    expect(screen.getByText(/Departing after 08:00 on 2026-11-16 · Weekday · Morning peak/)).toBeTruthy();
  });

  it("shows the no-journey empty state", () => {
    render(<Results response={mockNoJourneyResponse} />);
    expect(screen.getByTestId("no-journey").textContent).toContain("No scheduled journey departs within 60 min");
    expect(screen.queryByRole("tab")).toBeNull();
  });
});
