import { act, cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { useGameClock, useGameClockSource } from "./clock";

function ClockHarness({ active, serverClock }: { active: boolean; serverClock: number }) {
  useGameClockSource(active, serverClock);
  const clock = useGameClock();
  return <output data-testid="clock">{clock}</output>;
}

afterEach(() => {
  cleanup();
  vi.useRealTimers();
});

describe("isolated game clock store", () => {
  it("ticks clock consumers without requiring the source page to rerender", () => {
    vi.useFakeTimers();
    vi.setSystemTime(new Date("2026-08-24T00:00:00Z"));
    const view = render(<ClockHarness active serverClock={120} />);
    expect(screen.getByTestId("clock")).toHaveTextContent("120");

    act(() => {
      vi.advanceTimersByTime(1_000);
    });
    expect(screen.getByTestId("clock")).toHaveTextContent("121");
    view.unmount();
    expect(vi.getTimerCount()).toBe(0);
  });
});
