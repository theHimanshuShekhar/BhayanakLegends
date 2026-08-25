import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import type { ReactElement } from "react";
import { describe, expect, it, vi } from "vitest";
import { ChampSelectPage } from "../champ-select";
import { LiveMatchPage } from "../live-match";
import { PostGamePage } from "../postgame";
import { ProgressPage } from "../progress";
import { HistoryPage } from "../history";
import { ChampionsPage } from "../champions";

vi.mock("../../api/hooks", () => {
  const emptyQuery = () => ({
    data: undefined,
    error: null,
    isError: false,
    isLoading: false,
  });
  const emptyMutation = () => ({
    isError: false,
    isPending: false,
    isSuccess: false,
    mutate: vi.fn(),
  });
  return {
    useBenchmarks: emptyQuery,
    useCancelSync: emptyMutation,
    useHistorySummary: emptyQuery,
    useLiveIngame: emptyQuery,
    useLiveSession: emptyQuery,
    useLiveStatus: emptyQuery,
    usePack: emptyQuery,
    usePatchAggregates: emptyQuery,
    usePostgameLatest: emptyQuery,
    useSaveSettings: emptyMutation,
    useSettings: emptyQuery,
    useStartSync: emptyMutation,
    useSyncStatus: emptyQuery,
    useTrajectories: emptyQuery,
  };
});

vi.mock("../../api/sse", () => ({ useEvents: () => undefined }));

function renderRoute(ui: ReactElement) {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  return render(<QueryClientProvider client={queryClient}>{ui}</QueryClientProvider>);
}

describe("route document headings", () => {
  const routes = [
    ["Live Companion: Champ Select", <ChampSelectPage />],
    ["Live Companion: In Game", <LiveMatchPage />],
    ["Post-game Review", <PostGamePage />],
    ["Trajectory", <ProgressPage />],
    ["Improvement Journal", <HistoryPage />],
    ["Champion Evidence", <ChampionsPage />],
  ] as const;

  it.each(routes)("renders one canonical h1 for %s", (title, page) => {
    renderRoute(page);

    expect(screen.getAllByRole("heading", { level: 1 })).toHaveLength(1);
    expect(screen.getByRole("heading", { level: 1, name: title })).toHaveAttribute("tabindex", "-1");
  });
});
