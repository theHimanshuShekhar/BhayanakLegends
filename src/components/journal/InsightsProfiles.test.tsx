import { beforeEach, describe, expect, it, vi } from "vitest";
import { fireEvent, render, screen } from "@testing-library/react";
import type { UseQueryResult } from "@tanstack/react-query";
import { InsightsProfiles } from "./InsightsProfiles";
import { useHistoryInsights } from "../../api/hooks";
import type { HistoryInsights } from "../../api/types";

vi.mock("../../api/hooks", () => ({
  useHistoryInsights: vi.fn(),
}));

vi.mock("../../api/client", () => ({
  classifyApiError: vi.fn(() => "unknown"),
}));

const insights = vi.mocked(useHistoryInsights);
const windows = {
  latest: {
    name: "latest" as const,
    games: 6,
    wins: 3,
    win_rate: 0.5,
    sample_status: "review" as const,
    completeness: "partial" as const,
  },
  preceding: {
    name: "preceding" as const,
    games: 0,
    wins: 0,
    win_rate: 0,
    sample_status: "insufficient" as const,
    completeness: "unavailable" as const,
  },
};

const available: HistoryInsights = {
  feature_contract_version: "loltrends-parity-v2",
  feature_contract_status: "available",
  state: "available" as const,
  sample_size: 6,
  filters: { role: null, champion: null },
  roles: [
    { role: "MIDDLE" as const, games: 6, wins: 3, win_rate: 0.5, sample_status: "review" as const },
  ],
  champions: [
    {
      champion: "Ahri",
      games: 6,
      wins: 3,
      win_rate: 0.5,
      roles: ["MIDDLE" as const],
      sample_status: "review" as const,
    },
  ],
  windows,
};

const empty: HistoryInsights = {
  ...available,
  state: "empty",
  sample_size: 0,
  roles: [],
  champions: [],
  windows: {
    latest: {
      ...windows.latest,
      games: 0,
      wins: 0,
      win_rate: 0,
      sample_status: "insufficient",
      completeness: "unavailable",
    },
    preceding: {
      ...windows.preceding,
    },
  },
};

const queryState = (data: HistoryInsights) =>
  ({
    data,
    isLoading: false,
    isError: false,
    error: null,
  }) as unknown as UseQueryResult<HistoryInsights>;
beforeEach(() => {
  vi.clearAllMocks();
  insights.mockReturnValue(queryState(available));
});

describe("InsightsProfiles", () => {
  it("renders local role/champion profiles and a noisy review queue", () => {
    render(<InsightsProfiles />);

    expect(screen.getByTestId("journal-insights")).toHaveTextContent("6 filtered matches");
    expect(screen.getByTestId("insights-role-table")).toHaveTextContent("MIDDLE");
    expect(screen.getByTestId("insights-champion-table")).toHaveTextContent("Ahri");
    expect(screen.getByTestId("review-window-latest")).toHaveTextContent("6 of 50 matches");
    expect(screen.getByTestId("review-window-preceding")).toHaveTextContent("Not enough filtered history");
    expect(screen.getByText("No forecast: this noisy comparison only helps choose matches to inspect.")).toBeInTheDocument();
  });

  it("labels an empty filtered history without a population fallback", () => {
    insights.mockReturnValue(queryState(empty));
    render(<InsightsProfiles />);

    expect(screen.getByTestId("insights-empty")).toHaveTextContent("No Personal History yet");
    expect(screen.getByTestId("insights-empty")).toHaveTextContent("Population evidence is not used here.");
  });

  it("submits role and champion filters together", () => {
    render(<InsightsProfiles />);

    fireEvent.change(screen.getByTestId("insights-role-filter"), { target: { value: "MIDDLE" } });
    fireEvent.change(screen.getByTestId("insights-champion-filter"), { target: { value: "Ahri" } });
    fireEvent.click(screen.getByTestId("insights-apply-filter"));

    expect(insights).toHaveBeenLastCalledWith({ role: "MIDDLE", champion: "Ahri" });
  });
});
