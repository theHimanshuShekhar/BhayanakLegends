import type { PackV2ModelCard, PackV2SmokeTest } from "../../api/pack-v2";
import { describe, expect, it, vi, beforeEach } from "vitest";
import { act, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import type { ReactElement } from "react";
import type { SseMessage } from "../../api/sse";
import type { PostGameDigest, WhatIfResponse } from "../../api/types";
import { HistoryPage } from "../history";
import { api } from "../../api/client";
import { makeAvailablePersonalPack as makePack, makePack as makeCanonicalPack } from "./fixtures";
let sseHandler: ((msg: SseMessage) => void) | undefined;

vi.mock("../../api/client", async (importOriginal) => ({
  ...(await importOriginal<typeof import("../../api/client")>()),
  classifyApiError: () => "unknown",
  api: {
    health: vi.fn(),
    pack: vi.fn(),
    settings: vi.fn(),
    updateSettings: vi.fn(),
    startSync: vi.fn(),
    cancelSync: vi.fn(),
    syncStatus: vi.fn(),
    historySummary: vi.fn(),
    trajectories: vi.fn(),
    postgameLatest: vi.fn(),
    whatIf: vi.fn(),
    benchmarks: vi.fn(),
    liveStatus: vi.fn(),
  },
}));

vi.mock("../../api/sse", () => ({
  useEvents: vi.fn((cb?: (msg: SseMessage) => void) => {
    sseHandler = cb;
    return true;
  }),
}));

function renderPage(ui: ReactElement) {
  const qc = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  return render(<QueryClientProvider client={qc}>{ui}</QueryClientProvider>);
}

function activateOwnerFixture() {
  vi.mocked(api.settings).mockResolvedValue(activeSettings);
}

const summary = {
  matches: 128,
  patches: ["14.17", "15.5", "16.16"],
  by_role: [
    { role: "TOP" as const, games: 60, wins: 34 },
    { role: "JUNGLE" as const, games: 68, wins: 35 },
  ],
  win_rate: 0.54,
};

const ownerContext = {
  owner_key: null,
  generation: 0,
  owner_state: "unassigned" as const,
  owner_error: null,
};
const settings = {
  ...ownerContext,
  riot_id: null,
  region_route: "europe" as const,
  has_key: true,
  auto_sync: false,
};
const activeSettings = {
  ...settings,
  owner_key: "fixture-owner",
  generation: 1,
  owner_state: "active" as const,
  riot_id: "Initial#0001",
};

const savedSettings = {
  ...settings,
  owner_key: "fixture-owner",
  generation: 1,
  owner_state: "active" as const,
  riot_id: "Player#1234",
  region_route: "europe" as const,
  has_key: true,
  auto_sync: false,
};

const running = {
  state: "running" as const,
  mode: "era_first" as const,
  total_queued: 40,
  downloaded: 0,
  skipped: 0,
  failed: 0,
  current_match_id: null,
  started_at: "2026-08-24T10:00:00Z",
  owner_key: "fixture-owner",
  generation: 1,
  owner_state: "active" as const,
  owner_error: null,
};

beforeEach(() => {
  vi.clearAllMocks();
  sseHandler = undefined;
  vi.mocked(api.historySummary).mockResolvedValue(summary);
  vi.mocked(api.pack).mockResolvedValue(null as never);
  vi.mocked(api.postgameLatest).mockResolvedValue(null);
  vi.mocked(api.settings).mockResolvedValue(settings);
  vi.mocked(api.syncStatus).mockResolvedValue({
    ...running,
    state: "idle",
    total_queued: 0,
    started_at: null,
  });
});
const eligibleDigest: PostGameDigest = {
  match_id: "what-if-history-match",
  played_at: "2026-03-01T00:00:00Z",
  champion: "Ahri",
  role: "MIDDLE",
  win: true,
  duration_s: 1800,
  checkpoints: { gold_diff_10: 0, gold_diff_15: null, gold_diff_20: null },
  habits: [],
  headline: "Fixture Personal History match",
  feature_contract_version: "loltrends-parity-v2",
  personal_history_eligibility: "eligible",
  features: {
    cs10: 75,
    level10: 9.5,
    gold_diff_10: 0,
    team_gold_diff_15m: 0,
    recalls_before_15m: 2,
    avg_banked_gold_at_recall_by_15m: 650,
    avg_banked_gold_at_recall_by_20m: 700,
    unseen_recall_share_by_15m: 0.5,
    unseen_recall_share_by_20m: 0.5,
    first_dragon_by_20m_s: 600,
    first_riftherald_by_20m_s: 900,
    first_baron_by_20m_s: 0,
    early_fight_participation_rate: 0.5,
    plates_taken_by_14m: 7.5,
  },
  team_state: {
    feature: "team_gold_diff_15m",
    feature_contract_version: "loltrends-parity-v2",
    team_gold_diff_15m: 0,
    observed_through_s: 1200,
    non_surrendered: true,
  },
};

const availableWhatIfResponse: WhatIfResponse = {
  status: "available",
  probability: 0.6,
  baseline_probability: 0.5,
  adjusted_features: eligibleDigest.features as Record<string, number>,
  model_version: "synthetic-recall-v3-test-fixture",
  pack_version: "v7-personal-test-fixture",
  rejected_fields: [],
  reason: null,
};

describe("HistoryPage", () => {
  it("renders the summary stat row and by-role table", async () => {
    vi.mocked(api.settings).mockResolvedValue(activeSettings);
    renderPage(<HistoryPage />);

    expect(await screen.findByTestId("summary-matches")).toHaveTextContent("128");
    expect(screen.getByText("54.0%")).toBeInTheDocument();
    expect(screen.getByText("14.17 → 16.16")).toBeInTheDocument();

    const table = screen.getByTestId("by-role-table");
    expect(within(table).getByText("TOP")).toBeInTheDocument();
    expect(within(table).getByText("JUNGLE")).toBeInTheDocument();
    expect(within(table).getByText("56.7%")).toBeInTheDocument(); // 34/60
  });
  it("reports a failed history request without claiming the history is empty", async () => {
    vi.mocked(api.historySummary).mockRejectedValue(new Error("request failed"));
    renderPage(<HistoryPage />);
    expect(await screen.findByTestId("summary-error")).toHaveTextContent("Something went wrong. Check your settings and try again.");
    expect(screen.getByTestId("summary-error")).not.toHaveTextContent(/import|No local shards/);
  });

  it("preserves the required smoke vector on the TypeScript model-card mirror", () => {
    const card = makePack().models?.personal_what_if?.model_card;
    expect(card).not.toBeNull();
    if (!card) throw new Error("fixture model card is unavailable");
    const smokeTest: PackV2SmokeTest = card.smoke_test;
    const mirroredCard: PackV2ModelCard = card;
    expect(smokeTest.features).toHaveLength(mirroredCard.feature_order.length);
    expect(smokeTest.expected).toBeGreaterThanOrEqual(0);
    expect(smokeTest.expected).toBeLessThanOrEqual(1);
    expect(smokeTest.tolerance).toBeGreaterThanOrEqual(0);
  });

  it("seeds model controls from Personal History and shows model scope and caveats", async () => {
    activateOwnerFixture();
    vi.mocked(api.pack).mockResolvedValue(makePack());
    vi.mocked(api.postgameLatest).mockResolvedValue(eligibleDigest);
    vi.mocked(api.whatIf).mockResolvedValue(availableWhatIfResponse);
    renderPage(<HistoryPage />);

    const panel = await screen.findByTestId("what-if-panel");
    expect(screen.getAllByTestId("what-if-panel")).toHaveLength(1);
    await within(panel).findByTestId("what-if-model-scope");
    await waitFor(() => expect(within(panel).getByTestId("what-if-run")).not.toBeDisabled());
    const safeRecall = within(panel).getByTestId("what-if-control-unseen_recall_share_by_20m");
    const bankedGold = within(panel).getByTestId("what-if-control-avg_banked_gold_at_recall_by_20m");
    expect(within(panel).queryByTestId("what-if-control-plates_taken_by_14m")).toBeNull();
    expect(bankedGold).toHaveValue("700");
    expect(within(panel).getByTestId("what-if-plate-baseline")).toHaveTextContent(
      "Personal History plate value: 7.5 platesRead-only input to this model; this app does not offer plate adjustments.",
    );
    expect(within(panel).getByTestId("what-if-plate-evidence")).toHaveTextContent(
      "Population evidence: a-lite; weak, era-sensitive review context only.",
    );
    expect(within(panel).getByTestId("what-if-model-scope")).toHaveTextContent(
      "Model synthetic-recall-v3-test-fixture · Pack v7-personal-test-fixture · supported patches 14.17–16.17",
    );
    fireEvent.change(safeRecall, { target: { value: "0.75" } });
    fireEvent.click(within(panel).getByTestId("what-if-run"));
    await waitFor(() =>
      expect(api.whatIf).toHaveBeenCalledWith({
        unseen_recall_share_by_20m: 0.75,
        avg_banked_gold_at_recall_by_20m: 700,
      }),
    );
    await waitFor(() => expect(within(panel).getByTestId("what-if-prediction")).toHaveTextContent("60.0%"));
    expect(within(panel).getByTestId("what-if-provenance")).toHaveTextContent(
      "Model synthetic-recall-v3-test-fixture · Pack v7-personal-test-fixture",
    );
    expect(within(panel).getByTestId("what-if-caption")).toHaveTextContent(
      "Association model; not a causal guarantee.",
    );
    expect(within(panel).getByTestId("what-if-caption")).toHaveTextContent(
      "Inputs are accepted only from the declared bounded feature contract.",
    );
    fireEvent.change(safeRecall, { target: { value: "0.25" } });
    await waitFor(() => expect(within(panel).getByTestId("what-if-prediction")).toHaveTextContent("Unavailable"));
  });
  it("never exposes plates without population habit evidence", async () => {
    activateOwnerFixture();
    const pack = structuredClone(makePack());
    pack.habits = pack.habits.filter((habit) => habit.feature !== "plates_taken_by_14m");
    vi.mocked(api.pack).mockResolvedValue(pack);
    vi.mocked(api.postgameLatest).mockResolvedValue(eligibleDigest);
    renderPage(<HistoryPage />);

    const panel = await screen.findByTestId("what-if-panel");
    await waitFor(() => expect(within(panel).getByTestId("what-if-run")).not.toBeDisabled());
    expect(within(panel).queryByTestId("what-if-control-plates_taken_by_14m")).toBeNull();
    expect(within(panel).getByTestId("what-if-plate-baseline")).toHaveTextContent(
      "Personal History plate value: 7.5 platesRead-only input to this model; this app does not offer plate adjustments.",
    );
    expect(within(panel).getByTestId("what-if-plate-evidence")).toHaveTextContent(
      "Population evidence for plates is unavailable; no population comparison is shown.",
    );
    fireEvent.click(within(panel).getByTestId("what-if-run"));
    await waitFor(() => expect(api.whatIf).toHaveBeenCalledWith({
      unseen_recall_share_by_20m: 0.5,
      avg_banked_gold_at_recall_by_20m: 700,
    }));
  });

  it("does not claim a plate model input while the model is withheld", async () => {
    activateOwnerFixture();
    const pack = structuredClone(makePack());
    const declaration = pack.models?.personal_what_if;
    if (!declaration) throw new Error("fixture model declaration is unavailable");
    declaration.release_status = "withheld";
    declaration.model_card = null;
    declaration.release_reason = "Model release is withheld for review.";
    vi.mocked(api.pack).mockResolvedValue(pack);
    vi.mocked(api.postgameLatest).mockResolvedValue(eligibleDigest);
    renderPage(<HistoryPage />);

    await screen.findByText(/Model release is withheld for review/);
    const panel = screen.getByTestId("what-if-panel");
    expect(within(panel).queryByTestId("what-if-plate-baseline")).toBeNull();
    expect(within(panel).queryByTestId("what-if-plate-evidence")).toBeNull();
    expect(within(panel).queryByRole("slider")).toBeNull();
    expect(within(panel).getByTestId("what-if-run")).toBeDisabled();
  });
  it("keeps noncausal copy when a signed model card omits it and withholds a-lite plates", async () => {
    activateOwnerFixture();
    const pack = structuredClone(makePack());
    const declaration = pack.models?.personal_what_if;
    if (!declaration?.model_card) throw new Error("fixture model card is unavailable");
    declaration.model_card.caveats = ["A future signed-card caveat without causal wording."];
    vi.mocked(api.pack).mockResolvedValue(pack);
    vi.mocked(api.postgameLatest).mockResolvedValue(eligibleDigest);
    vi.mocked(api.whatIf).mockResolvedValue(availableWhatIfResponse);
    renderPage(<HistoryPage />);

    const panel = await screen.findByTestId("what-if-panel");
    await waitFor(() => expect(within(panel).getByTestId("what-if-run")).not.toBeDisabled());
    expect(within(panel).queryByTestId("what-if-control-plates_taken_by_14m")).toBeNull();
    fireEvent.click(within(panel).getByTestId("what-if-run"));
    await waitFor(() => expect(api.whatIf).toHaveBeenCalled());
    await waitFor(() =>
      expect(within(panel).getByTestId("what-if-prediction")).toHaveTextContent("60.0%"),
    );
    expect(within(panel).getByTestId("what-if-current")).toHaveTextContent("50.0%");
    expect(within(panel).getByTestId("what-if-caption")).toHaveTextContent(
      "A future signed-card caveat without causal wording.",
    );
    expect(within(panel).getByTestId("what-if-caption")).toHaveTextContent(
      "Association only; not causal.",
    );
  });


  it("suppresses controls when the personal seed is outside model-card bounds", async () => {
    activateOwnerFixture();
    vi.mocked(api.pack).mockResolvedValue(makePack());
    vi.mocked(api.postgameLatest).mockResolvedValue({
      ...eligibleDigest,
      features: { ...eligibleDigest.features, unseen_recall_share_by_20m: 1.1 },
    });
    renderPage(<HistoryPage />);
    const panel = await screen.findByTestId("what-if-panel");
    await within(panel).findByTestId("what-if-model-scope");
    await waitFor(() =>
      expect(within(panel).getByText("This Personal History value is outside the declared model domain.")).toBeInTheDocument(),
    );
    expect(within(panel).getByText("This Personal History value is outside the declared model domain.")).toBeInTheDocument();
    expect(within(panel).queryByTestId("what-if-control-unseen_recall_share_by_20m")).toBeNull();
    expect(within(panel).getByTestId("what-if-run")).toBeDisabled();
    expect(within(panel).getByTestId("what-if-current")).toHaveTextContent("Unavailable");
    expect(within(panel).getByTestId("what-if-prediction")).toHaveTextContent("Unavailable");
    expect(within(panel).getByTestId("what-if-caption")).toHaveTextContent(
      "complete finite baseline inside the model-card domains",
    );
  });

  it("dresses the screen in the design system shells and pill buttons", async () => {
    renderPage(<HistoryPage />);

    const syncPanel = await screen.findByTestId("sync-panel");
    expect(syncPanel).toHaveClass("card3b");

    // canonical action hierarchy: Start Backfill primary lavender, Save settings secondary, Cancel tertiary
    const start = screen.getByTestId("start-sync");
    expect(start).toHaveClass("pill");
    expect(start).toHaveStyle({ background: "var(--color-accent)" });

    const save = screen.getByTestId("save-settings");
    expect(save).toHaveClass("pill");
    expect(save).toHaveStyle({ background: "var(--color-surface-2)" });
    expect(save).toHaveStyle({ color: "var(--color-dim)" });

    const cancel = screen.getByTestId("cancel-sync");
    expect(cancel).toHaveClass("pill");
    expect(cancel).toBeDisabled();
    expect(cancel).toHaveStyle({ background: "transparent" });
  });

  it("shows an empty identity and requires it before Backfill", async () => {
    renderPage(<HistoryPage />);

    const riotId = await screen.findByTestId("input-riot-id");
    const region = screen.getByTestId("input-region");
    await waitFor(() => expect(region).toHaveValue("europe"));
    expect(riotId).toHaveValue("");
    // pristine render: initially blank/default data shows no eager validation error
    expect(screen.queryByTestId("riot-id-error")).toBeNull();
    expect(riotId).toHaveAttribute("aria-invalid", "false");

    // saved settings carry no identity yet: Backfill stays gated behind a visible linked reason
    const startBtn = screen.getByTestId("start-sync");
    expect(startBtn).toBeDisabled();
    expect(startBtn).toHaveAttribute("aria-describedby", "start-disabled-reason");
    expect(screen.getByTestId("start-disabled-reason")).toBeVisible();
    expect(screen.getByTestId("input-riot-key")).toHaveAttribute(
      "placeholder",
      "saved — leave blank to keep",
    );

    // blurring an invalid value reveals exactly one associated error
    fireEvent.blur(riotId);
    expect(screen.getByTestId("riot-id-error")).toHaveTextContent("GameName#TAG");
    expect(riotId).toHaveAttribute("aria-invalid", "true");
    expect(riotId).toHaveAttribute("aria-describedby", "riot-id-error");

    // entering a valid id clears it immediately
    fireEvent.change(riotId, { target: { value: "Player#1234" } });
    expect(screen.queryByTestId("riot-id-error")).toBeNull();
    expect(riotId).toHaveAttribute("aria-invalid", "false");
    expect(riotId).not.toHaveAttribute("aria-describedby");
  });

  it("starts a sync only after an explicit identity is saved", async () => {
    vi.mocked(api.settings).mockResolvedValue(activeSettings);
    vi.mocked(api.startSync).mockResolvedValue(running);
    vi.mocked(api.updateSettings).mockResolvedValue(savedSettings);
    renderPage(<HistoryPage />);

    const startBtn = await screen.findByTestId("start-sync");
    expect(startBtn).toBeDisabled();

    // typing alone leaves local edits unsaved: clicking Start must not fire against stale settings
    fireEvent.change(screen.getByTestId("input-riot-id"), {
      target: { value: "Player#1234" },
    });
    expect(startBtn).toBeDisabled();
    expect(screen.getByTestId("start-disabled-reason")).toHaveTextContent(
      "Save settings before starting Backfill.",
    );
    fireEvent.click(startBtn);
    expect(api.startSync).not.toHaveBeenCalled();

    // saving persists the identity and unlocks Backfill
    fireEvent.click(screen.getByTestId("save-settings"));
    await waitFor(() => expect(api.updateSettings).toHaveBeenCalledTimes(1));
    await waitFor(() => expect(startBtn).not.toBeDisabled());
    expect(await screen.findByTestId("save-ok")).toBeInTheDocument();

    fireEvent.click(startBtn);
    await waitFor(() => expect(api.startSync).toHaveBeenCalledTimes(1));
    await waitFor(() =>
      expect(screen.getByTestId("start-disabled-reason")).toHaveTextContent(
        "Backfill is running.",
      ),
    );
    expect(startBtn).toBeDisabled();
    expect(screen.getByText(/Current-patch games download first/)).toBeInTheDocument();
  });


  it("updates the progress bar from SSE sync.progress events", async () => {
    vi.mocked(api.settings).mockResolvedValue(activeSettings);
    vi.mocked(api.startSync).mockResolvedValue(running);
    vi.mocked(api.updateSettings).mockResolvedValue(savedSettings);
    renderPage(<HistoryPage />);

    fireEvent.change(await screen.findByTestId("input-riot-id"), {
      target: { value: "Player#1234" },
    });
    fireEvent.click(screen.getByTestId("save-settings"));
    await waitFor(() => expect(api.updateSettings).toHaveBeenCalledTimes(1));
    await waitFor(() => expect(screen.getByTestId("start-sync")).not.toBeDisabled());
    fireEvent.click(screen.getByTestId("start-sync"));
    await waitFor(() => expect(api.startSync).toHaveBeenCalled());

    await act(async () => {
      sseHandler?.({
        type: "sync.progress",
        ts: new Date().toISOString(),
        data: { ...running, downloaded: 12, failed: 1, current_match_id: "EUW1_999" },
      });
    });
    const bar = screen.getByTestId("sync-progress-bar");
    await waitFor(() => {
      expect(bar).toHaveStyle({ width: "30%" }); // 12 / 40
      expect(screen.getByTestId("sync-counters")).toHaveTextContent("12 / 40 matches");
      expect(screen.getByTestId("sync-counters")).toHaveTextContent("1 failed");
      expect(screen.getByTestId("sync-current")).toHaveTextContent("EUW1_999");
    });

    // terminal event flips the bar to its done color
    await act(async () => {
      sseHandler?.({
        type: "sync.done",
        ts: new Date().toISOString(),
        data: { ...running, state: "idle", downloaded: 40 },
      });
    });
    await waitFor(() => expect(bar.className).toContain("bg-teal"));
  });
});

it("withholds canonical personal controls", async () => {
  activateOwnerFixture();
  vi.mocked(api.pack).mockResolvedValue(makeCanonicalPack());
  vi.mocked(api.postgameLatest).mockResolvedValue(eligibleDigest);
  renderPage(<HistoryPage />);
  await waitFor(() => expect(screen.getByTestId("what-if-run")).toBeDisabled());
  expect(screen.queryByTestId("what-if-control-unseen_recall_share_by_20m")).toBeNull();
});

it("disables inference for an installed obsolete recall model contract", async () => {
  activateOwnerFixture();
  const historical = structuredClone(makePack());
  historical.feature_contracts.models!.personal_what_if = "loltrends-cutoff-v2";
  historical.models!.personal_what_if.model_card!.feature_contract_version = "loltrends-cutoff-v2";
  vi.mocked(api.pack).mockResolvedValue(historical);
  vi.mocked(api.postgameLatest).mockResolvedValue(eligibleDigest);
  renderPage(<HistoryPage />);
  await waitFor(() => expect(screen.getByTestId("what-if-run")).toBeDisabled());
  expect(api.whatIf).not.toHaveBeenCalled();
});
