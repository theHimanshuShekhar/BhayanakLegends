import { describe, expect, it } from "vitest";
import { render, screen } from "@testing-library/react";
import { FeatureInsights } from "./FeatureInsights";
import type { HistoryFeatureInsight, HistoryFeatureTrajectoryPoint } from "../../api/types";

const available: HistoryFeatureInsight = {
  feature_key: "early_fight_participation_rate",
  current_value: 0.375,
  role_baseline: 0.32,
  delta: 0.055,
  sample_size: 8,
  status: "available",
  caveat: "Diagnostic association in a small local sample.",
};

const unavailable: HistoryFeatureInsight = {
  feature_key: "first_dragon_by_20m_s",
  current_value: null,
  role_baseline: null,
  delta: null,
  sample_size: 2,
  status: "insufficient-sample",
  caveat: "At least five matching-role observations are required.",
};

const points: HistoryFeatureTrajectoryPoint[] = [
  {
    feature_key: "plates_taken_by_14m",
    played_at: "2026-08-01T00:00:00Z",
    value: 2,
    sample_size: 1,
    status: "available",
    caveat: "Weak, era-sensitive diagnostic association; the 14.x direction differs and is not significant; not a causal recommendation.",
  },
  {
    feature_key: "plates_taken_by_14m",
    played_at: "2026-08-02T00:00:00Z",
    value: null,
    sample_size: 1,
    status: "unavailable",
    caveat: "The 14-minute observation window was not reached.",
  },
];

describe("FeatureInsights", () => {
  it("renders role-adjusted values and keeps the caveat descriptive", () => {
    render(<FeatureInsights insights={[available]} trajectories={[]} />);

    const row = screen.getByTestId("feature-insight-early_fight_participation_rate");
    expect(row).toHaveTextContent("Early-fight participation");
    expect(row).toHaveTextContent("37.5%");
    expect(row).toHaveTextContent("matching-role reference 32.0%");
    expect(row).toHaveTextContent("difference +5.5%");
    expect(row).toHaveTextContent("Diagnostic association in a small local sample.");
    expect(row).not.toHaveTextContent(/do more|fight more|must/i);
  });

  it("renders an explicit unavailable state instead of a fabricated timing value", () => {
    render(<FeatureInsights insights={[unavailable]} trajectories={[]} />);

    const row = screen.getByTestId("feature-insight-first_dragon_by_20m_s");
    expect(row).toHaveTextContent("Unavailable:");
    expect(row).toHaveTextContent("At least five matching-role observations are required.");
    expect(row).not.toHaveTextContent(/\d+:\d+/);
  });

  it("renders available trajectory points with the feature caveat", () => {
    render(<FeatureInsights insights={[]} trajectories={points} />);

    const card = screen.getByTestId("feature-trajectory-plates_taken_by_14m");
    expect(card).toHaveTextContent("2 plates");
    expect(card).toHaveTextContent("2026-08-01");
    expect(card).toHaveTextContent(/the 14\.x direction differs and is not significant/i);
    expect(screen.getByTestId("journal-feature-insights")).toHaveAttribute(
      "aria-labelledby",
      "journal-feature-insights-heading",
    );
  });
});
