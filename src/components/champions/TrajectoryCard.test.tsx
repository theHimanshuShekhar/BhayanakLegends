import { describe, expect, it } from "vitest";
import { cleanup, render, screen } from "@testing-library/react";
import type { PatchAggregate, TrajectoryPoint } from "../../api/types";
import { TrajectoryCard } from "./TrajectoryCard";

const point = (patch: string, index: number, rolling_wr: number, played_at: string): TrajectoryPoint => ({
  patch,
  role: "MIDDLE",
  champion: "Ahri",
  played_at,
  index,
  rolling_wr,
});

const aggregates: PatchAggregate[] = [
  { patch: "14.17", games: 4, wins: 3, win_rate: 0.75 },
];

describe("TrajectoryCard", () => {
  it("guides selection without plotting an unselected champion", () => {
    render(<TrajectoryCard champion={null} points={[]} aggregates={[]} />);

    expect(screen.getByTestId("trajectory-selection-guidance")).toHaveTextContent("Select a champion");
    expect(screen.queryByTestId("trajectory-svg")).not.toBeInTheDocument();
  });

  it("shows Backfill for zero points and renders a single point without a polyline", () => {
    render(<TrajectoryCard champion="Ahri" points={[]} aggregates={[]} />);
    expect(screen.getByTestId("trajectory-empty")).toHaveTextContent("Backfill");
    cleanup();
    render(
      <TrajectoryCard
        champion="Ahri"
        points={[point("14.17", 0, 0.62, "2026-01-01T00:00:00Z")]}
        aggregates={aggregates}
      />,
    );
    expect(screen.getByTestId("trajectory-svg").querySelector("circle")).toBeInTheDocument();
    expect(screen.getByTestId("trajectory-svg").querySelector("polyline")).not.toBeInTheDocument();
  });

  it("plots every rolling point chronologically, including duplicate patches", () => {
    render(
      <TrajectoryCard
        champion="Ahri"
        points={[
          point("16.16", 2, 0.4, "2026-02-01T00:00:00Z"),
          point("14.17", 0, 0.6, "2026-01-01T00:00:00Z"),
          point("14.17", 1, 0.5, "2026-01-02T00:00:00Z"),
        ]}
        aggregates={aggregates}
      />,
    );

    const svg = screen.getByTestId("trajectory-svg");
    expect(svg.querySelector("polyline")).toHaveAttribute("points", "0,30 150,36 300,42");
    expect(screen.getAllByText("14.17")).toHaveLength(3);
  });

  it("keeps aggregate wins, games, and rates separate from the rolling line", () => {
    render(
      <TrajectoryCard
        champion="Ahri"
        points={[point("14.17", 0, 0.62, "2026-01-01T00:00:00Z")]}
        aggregates={aggregates}
      />,
    );

    expect(screen.getByTestId("trajectory-aggregates")).toHaveTextContent("3 wins · 4 games · 75.0%");
    expect(screen.getByTestId("trajectory-card")).toHaveTextContent("Personal History");
  });

  it("reports trajectory and aggregate errors independently", () => {
    render(
      <TrajectoryCard
        champion="Ahri"
        points={[]}
        aggregates={[]}
        trajectoryError="trajectory unavailable"
        aggregateError="aggregate unavailable"
      />,
    );

    expect(screen.getByTestId("trajectory-card")).toHaveTextContent("Trajectory: trajectory unavailable");
    expect(screen.getByTestId("trajectory-card")).toHaveTextContent("Patch aggregates: aggregate unavailable");
  });
});
