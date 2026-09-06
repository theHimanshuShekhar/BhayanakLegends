import { describe, expect, it, vi, beforeEach } from "vitest";
import { act, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import type { SseMessage } from "../../api/sse";
import { SyncPanel } from "./SyncPanel";
import { api } from "../../api/client";

let sseHandler: ((msg: SseMessage) => void) | undefined;

vi.mock("../../api/client", () => ({
  actionableErrorMessage: (error: unknown) =>
    error instanceof Error && error.message.includes("offline")
      ? "The sidecar is offline. Reopen the app and try again."
      : "Something went wrong. Check your settings and try again.",
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

function deferred<T>() {
  let resolve!: (value: T) => void;
  const promise = new Promise<T>((complete) => {
    resolve = complete;
  });
  return { promise, resolve };
}

function renderPanel(queryClient = new QueryClient({
  defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
})) {
  const rendered = render(
    <QueryClientProvider client={queryClient}>
      <SyncPanel />
    </QueryClientProvider>,
  );
  return { queryClient, ...rendered };
}

const ownerContext = {
  owner_key: "fixture-owner",
  generation: 1,
  owner_state: "active" as const,
  owner_error: null,
};
const settings = {
  ...ownerContext,
  riot_id: "FixturePlayer03#BL03",
  region_route: "sea",
  has_key: false,
  auto_sync: true,
} as const;
const idle = {
  state: "idle" as const,
  mode: "era_first" as const,
  total_queued: 0,
  downloaded: 0,
  skipped: 0,
  failed: 0,
  current_match_id: null,
  started_at: null,
  ...ownerContext,
};
const running = {
  state: "running" as const,
  mode: "era_first" as const,
  total_queued: 25,
  downloaded: 5,
  skipped: 0,
  failed: 0,
  current_match_id: "EUW1_1",
  started_at: "2026-08-24T10:00:00Z",
  ...ownerContext,
};

beforeEach(() => {
  vi.clearAllMocks();
  sseHandler = undefined;
  vi.mocked(api.settings).mockResolvedValue(settings);
  vi.mocked(api.syncStatus).mockResolvedValue(idle);
});

describe("SyncPanel", () => {
  it("shows the era-first explainer", async () => {
    renderPanel();
    expect(
      await screen.findByText("Current-patch games download first; older history fills in across sessions."),
    ).toBeInTheDocument();
  });

  it("surfaces the saved-key prerequisite for auto-sync", async () => {
    renderPanel();

    expect(await screen.findByTestId("auto-sync-prerequisite")).toHaveTextContent(
      "Save a Riot API key to enable auto-sync when the app opens.",
    );
  });

  it("keeps pristine Riot ID quiet, then associates blur validation and clears it on valid input", async () => {
    vi.mocked(api.settings).mockResolvedValue({ ...settings, riot_id: null });
    renderPanel();

    const riotId = await screen.findByTestId("input-riot-id");
    expect(screen.queryByTestId("riot-id-error")).toBeNull();
    expect(riotId).toHaveAttribute("aria-invalid", "false");
    expect(riotId).not.toHaveAttribute("aria-describedby");

    fireEvent.blur(riotId);
    const error = await screen.findByTestId("riot-id-error");
    expect(error).toHaveTextContent("Enter a valid GameName#TAG before starting Backfill.");
    expect(riotId).toHaveAttribute("aria-invalid", "true");
    expect(riotId).toHaveAttribute("aria-describedby", error.id);

    fireEvent.change(riotId, { target: { value: "FixturePlayer03#BL03" } });
    expect(screen.queryByTestId("riot-id-error")).toBeNull();
    expect(riotId).toHaveAttribute("aria-invalid", "false");
    expect(riotId).not.toHaveAttribute("aria-describedby");
  });
  it("reveals validation on Save and keeps Start disabled with one accessible reason", async () => {
    vi.mocked(api.settings).mockResolvedValue({ ...settings, riot_id: null });
    renderPanel();

    const saveButton = await screen.findByTestId("save-settings");
    fireEvent.click(saveButton);

    expect(await screen.findByTestId("riot-id-error")).toBeInTheDocument();
    expect(api.updateSettings).not.toHaveBeenCalled();
    const startButton = screen.getByTestId("start-sync");
    expect(startButton).toBeDisabled();
    expect(screen.getByTestId("start-disabled-reason")).toHaveTextContent(
      "Enter a valid Riot ID before starting Backfill.",
    );
  });

  it("requires saved settings before starting and makes Start the sole primary action", async () => {
    renderPanel();

    const startButton = await screen.findByTestId("start-sync");
    await waitFor(() => expect(startButton).not.toBeDisabled());
    expect(startButton).toHaveTextContent("Start Backfill");
    expect(startButton).toHaveStyle({ background: "var(--color-accent)" });
    expect(screen.getByTestId("save-settings")).toHaveTextContent("Save settings");
    expect(screen.getByTestId("save-settings")).toHaveStyle({ background: "var(--color-surface-2)" });
    expect(screen.getByTestId("cancel-sync")).toBeDisabled();
  });

  it("blocks Start while local settings are dirty until Save completes", async () => {
    renderPanel();
    const riotId = await screen.findByTestId("input-riot-id");
    await waitFor(() => expect(riotId).toHaveValue(settings.riot_id));
    fireEvent.change(riotId, { target: { value: "OtherPlayer#BL04" } });

    expect(screen.getByTestId("start-sync")).toBeDisabled();
    expect(screen.getByTestId("start-disabled-reason")).toHaveTextContent(
      "Save settings before starting Backfill.",
    );
    fireEvent.click(screen.getByTestId("start-sync"));
    expect(api.startSync).not.toHaveBeenCalled();
  });
  it("uses Loading… while a Backfill request is in flight and retains an accessible reason", async () => {
    vi.mocked(api.startSync).mockImplementation(() => new Promise(() => {}));
    renderPanel();

    const startButton = await screen.findByTestId("start-sync");
    await waitFor(() => expect(startButton).not.toBeDisabled());
    fireEvent.click(startButton);

    await waitFor(() => expect(startButton).toBeDisabled());
    expect(screen.getByTestId("start-disabled-reason")).toHaveTextContent("Loading…");
    expect(screen.getByTestId("backfill-source-status")).toHaveTextContent("Loading…");
  });

  it("shows actionable server errors without changing the sync contract", async () => {
    vi.mocked(api.startSync).mockRejectedValue(new Error("sidecar offline"));
    renderPanel();

    const startButton = await screen.findByTestId("start-sync");
    await waitFor(() => expect(startButton).not.toBeDisabled());
    fireEvent.click(startButton);

    expect(await screen.findByTestId("start-error")).toHaveTextContent(
      "The sidecar is offline. Reopen the app and try again.",
    );
    expect(api.startSync).toHaveBeenCalledTimes(1);
  });

  it("saves settings via PUT, including a typed key, and shows inline confirmation", async () => {
    vi.mocked(api.updateSettings).mockResolvedValue(settings);
    renderPanel();

    fireEvent.change(await screen.findByTestId("input-riot-key"), {
      target: { value: "RGAPI-test" },
    });
    fireEvent.click(screen.getByTestId("save-settings"));

    await waitFor(() => expect(api.updateSettings).toHaveBeenCalledTimes(1));
    expect(api.updateSettings).toHaveBeenCalledWith({
      riot_id: "FixturePlayer03#BL03",
      region_route: "sea",
      auto_sync: true,
      riot_key: "RGAPI-test",
    });
    expect(await screen.findByTestId("save-ok")).toBeInTheDocument();
  });

  it("reflects polled sync status and overlays fresher SSE progress", async () => {
    vi.mocked(api.startSync).mockResolvedValue(running);
    renderPanel();

    // polled fallback shows zero progress
    await waitFor(() => expect(screen.getByTestId("sync-counters")).toHaveTextContent("0 / 0"));

    fireEvent.click(screen.getByTestId("start-sync"));
    await waitFor(() => expect(api.startSync).toHaveBeenCalledTimes(1));

    // SSE overlay: 10 of 25 downloaded -> 40%
    await act(async () => {
      sseHandler?.({
        type: "sync.progress",
        ts: new Date().toISOString(),
        data: { ...running, downloaded: 10 },
      });
    });

    const bar = screen.getByTestId("sync-progress-bar");
    await waitFor(() => expect(bar).toHaveStyle({ width: "40%" }));
    expect(screen.getByTestId("sync-current")).toHaveTextContent("EUW1_1");
    await act(async () => {
      sseHandler?.({
        type: "sync.progress",
        ts: new Date().toISOString(),
        data: { ...running, total_queued: 2500, downloaded: 1200 },
      });
    });
    await waitFor(() => expect(screen.getByTestId("sync-counters")).toHaveTextContent("1,200 / 2,500 matches"));

    // while running, Start is disabled and Cancel is armed
    expect(screen.getByTestId("start-sync")).toBeDisabled();
    expect(screen.getByTestId("cancel-sync")).not.toBeDisabled();
  });
  it("recovers idle → running → completed through successive polls when SSE is unavailable", async () => {
    const completed = {
      ...running,
      state: "idle" as const,
      downloaded: 25,
      current_match_id: null,
    };
    const { queryClient } = renderPanel();

    await waitFor(() => expect(screen.getByTestId("sync-counters")).toHaveTextContent("0 / 0 matches"));

    vi.mocked(api.syncStatus).mockResolvedValueOnce(running);
    await act(async () => {
      await queryClient.invalidateQueries({ queryKey: ["sync-status"] });
    });
    await waitFor(() => expect(screen.getByTestId("sync-counters")).toHaveTextContent("5 / 25 matches"));
    expect(screen.getByTestId("start-sync")).toBeDisabled();
    expect(screen.getByTestId("cancel-sync")).not.toBeDisabled();

    vi.mocked(api.syncStatus).mockResolvedValueOnce(completed);
    await act(async () => {
      await queryClient.invalidateQueries({ queryKey: ["sync-status"] });
    });
    await waitFor(() => expect(screen.getByTestId("sync-counters")).toHaveTextContent("25 / 25 matches"));
    expect(screen.getByTestId("start-sync")).not.toBeDisabled();
    expect(screen.getByTestId("cancel-sync")).toBeDisabled();
  });
  it("recovers idle → running → failed through successive polls without claiming completion", async () => {
    const failed = {
      ...running,
      state: "error" as const,
      downloaded: 8,
      current_match_id: null,
    };
    const { queryClient } = renderPanel();

    await waitFor(() => expect(screen.getByTestId("sync-counters")).toHaveTextContent("0 / 0 matches"));

    vi.mocked(api.syncStatus).mockResolvedValueOnce(running);
    await act(async () => {
      await queryClient.invalidateQueries({ queryKey: ["sync-status"] });
    });
    await waitFor(() => expect(screen.getByTestId("sync-counters")).toHaveTextContent("5 / 25 matches"));

    vi.mocked(api.syncStatus).mockResolvedValueOnce(failed);
    await act(async () => {
      await queryClient.invalidateQueries({ queryKey: ["sync-status"] });
    });
    await waitFor(() => expect(screen.getByTestId("sync-status-error")).toBeInTheDocument());
    expect(screen.getByTestId("sync-counters")).toHaveTextContent("8 / 25 matches");
    expect(screen.getByTestId("start-sync")).not.toBeDisabled();
    expect(screen.getByTestId("cancel-sync")).toBeDisabled();
  });
  it("keeps an event-driven running state over a stale idle poll, then accepts a later current poll", async () => {
    const firstPoll = deferred<typeof idle>();
    const completed = {
      ...running,
      state: "idle" as const,
      downloaded: 25,
      current_match_id: null,
    };
    vi.mocked(api.syncStatus).mockReturnValueOnce(firstPoll.promise);
    const { queryClient } = renderPanel();

    await waitFor(() => expect(api.syncStatus).toHaveBeenCalledTimes(1));
    await act(async () => {
      sseHandler?.({
        type: "sync.progress",
        ts: "event-running",
        data: running,
      });
    });
    await waitFor(() => expect(screen.getByTestId("sync-counters")).toHaveTextContent("5 / 25 matches"));
    expect(screen.getByTestId("cancel-sync")).not.toBeDisabled();

    firstPoll.resolve(idle);
    await act(async () => {
      await firstPoll.promise;
    });
    expect(screen.getByTestId("sync-counters")).toHaveTextContent("5 / 25 matches");

    vi.mocked(api.syncStatus).mockResolvedValueOnce(completed);
    await act(async () => {
      await queryClient.invalidateQueries({ queryKey: ["sync-status"] });
    });
    await waitFor(() => expect(screen.getByTestId("sync-counters")).toHaveTextContent("25 / 25 matches"));
    expect(screen.getByTestId("start-sync")).not.toBeDisabled();
  });
  it("refreshes owner state from status polls after resolution completes", async () => {
    const resolvingOwner = {
      owner_key: null,
      generation: 2,
      owner_state: "resolving" as const,
      owner_error: null,
    };
    const activeOwner = {
      owner_key: "resolved-owner",
      generation: 2,
      owner_state: "active" as const,
      owner_error: null,
    };
    const resolvingSettings = { ...settings, ...resolvingOwner };
    const resolvingStatus = { ...idle, ...resolvingOwner };
    const activeStatus = { ...idle, ...activeOwner };
    vi.mocked(api.settings).mockResolvedValue(resolvingSettings);
    vi.mocked(api.syncStatus).mockResolvedValueOnce(resolvingStatus);
    const { queryClient } = renderPanel();

    await waitFor(() =>
      expect(screen.getByTestId("sync-owner-status")).toHaveTextContent("Resolving Riot account…"),
    );
    await waitFor(() => expect(api.syncStatus).toHaveBeenCalledTimes(1));

    vi.mocked(api.syncStatus).mockResolvedValueOnce(activeStatus);
    await act(async () => {
      await queryClient.invalidateQueries({ queryKey: ["sync-status"] });
    });

    await waitFor(() => expect(screen.getByTestId("sync-owner-status")).toHaveTextContent("Riot account active."));
    expect(screen.getByTestId("start-sync")).not.toBeDisabled();
  });
  it("refreshes owner errors from status polls without showing prior queue data", async () => {
    const resolvingOwner = {
      owner_key: null,
      generation: 3,
      owner_state: "resolving" as const,
      owner_error: null,
    };
    const errorOwner = {
      owner_key: null,
      generation: 3,
      owner_state: "error" as const,
      owner_error: "Riot ID could not be resolved",
    };
    vi.mocked(api.settings).mockResolvedValue({ ...settings, ...resolvingOwner });
    vi.mocked(api.syncStatus).mockResolvedValueOnce({ ...idle, ...resolvingOwner });
    const { queryClient } = renderPanel();

    await waitFor(() =>
      expect(screen.getByTestId("sync-owner-status")).toHaveTextContent("Resolving Riot account…"),
    );
    vi.mocked(api.syncStatus).mockResolvedValueOnce({ ...idle, ...errorOwner });
    await act(async () => {
      await queryClient.invalidateQueries({ queryKey: ["sync-status"] });
    });

    await waitFor(() =>
      expect(screen.getByTestId("sync-owner-status")).toHaveTextContent(
        "Unavailable: Riot account resolution failed — Riot ID could not be resolved",
      ),
    );
    expect(screen.queryByTestId("sync-progress")).toBeNull();
    expect(screen.getByTestId("start-sync")).toBeDisabled();
  });
  it("detaches an old-owner poll and event when settings switch generations", async () => {
    const oldPoll = deferred<typeof running>();
    const nextOwnerContext = {
      owner_key: "next-owner",
      generation: 2,
      owner_state: "active" as const,
      owner_error: null,
    };
    const nextSettings = {
      ...nextOwnerContext,
      riot_id: "NextPlayer04#BL04",
      region_route: "europe" as const,
      has_key: false,
      auto_sync: true,
    };
    const nextIdle = { ...idle, ...nextOwnerContext };
    vi.mocked(api.syncStatus).mockReturnValueOnce(oldPoll.promise);
    const { queryClient } = renderPanel();
    await waitFor(() => expect(api.syncStatus).toHaveBeenCalledTimes(1));

    vi.mocked(api.settings).mockResolvedValueOnce(nextSettings);
    vi.mocked(api.syncStatus).mockResolvedValueOnce(running);
    await act(async () => {
      await queryClient.invalidateQueries({ queryKey: ["settings"] });
    });
    await waitFor(() => expect(screen.getByTestId("input-riot-id")).toHaveValue(nextSettings.riot_id));
    await waitFor(() => expect(screen.queryByTestId("sync-progress")).toBeNull());

    vi.mocked(api.syncStatus).mockResolvedValueOnce(nextIdle);
    await act(async () => {
      await queryClient.invalidateQueries({ queryKey: ["sync-status"] });
    });
    await waitFor(() => expect(screen.getByTestId("sync-counters")).toHaveTextContent("0 / 0 matches"));

    await act(async () => {
      sseHandler?.({
        type: "sync.progress",
        ts: "old-owner-event",
        data: running,
      });
    });
    oldPoll.resolve(running);
    await act(async () => {
      await oldPoll.promise;
    });

    expect(screen.getByTestId("input-riot-id")).toHaveValue(nextSettings.riot_id);
    expect(screen.getByTestId("sync-counters")).toHaveTextContent("0 / 0 matches");
    expect(screen.queryByTestId("sync-current")).toBeNull();
  });
  it("does not let a delayed running poll undo a newer completed event", async () => {
    const delayedPoll = deferred<typeof running>();
    const completed = {
      ...running,
      state: "idle" as const,
      downloaded: 25,
      current_match_id: null,
    };
    const { queryClient } = renderPanel();
    await waitFor(() => expect(screen.getByTestId("sync-counters")).toHaveTextContent("0 / 0 matches"));

    vi.mocked(api.syncStatus).mockReturnValueOnce(delayedPoll.promise);
    let refresh!: Promise<void>;
    await act(async () => {
      refresh = queryClient.invalidateQueries({ queryKey: ["sync-status"] });
      await Promise.resolve();
    });
    await waitFor(() => expect(api.syncStatus).toHaveBeenCalledTimes(2));

    await act(async () => {
      sseHandler?.({
        type: "sync.done",
        ts: "event-completed",
        data: completed,
      });
    });
    await waitFor(() => expect(screen.getByTestId("sync-counters")).toHaveTextContent("25 / 25 matches"));
    expect(screen.getByTestId("cancel-sync")).toBeDisabled();

    delayedPoll.resolve(running);
    await act(async () => {
      await delayedPoll.promise;
      await refresh;
    });
    expect(screen.getByTestId("sync-counters")).toHaveTextContent("25 / 25 matches");
    expect(screen.getByTestId("cancel-sync")).toBeDisabled();
  });
  it("lets a newer start acknowledgement reset progress while ignoring an older poll", async () => {
    const previousRun = {
      ...running,
      state: "idle" as const,
      downloaded: 25,
      current_match_id: null,
    };
    const delayedPoll = deferred<typeof running>();
    const nextRun = {
      ...running,
      downloaded: 0,
      current_match_id: "EUW1_2",
      started_at: "2026-08-24T11:00:00Z",
    };
    vi.mocked(api.syncStatus).mockResolvedValueOnce(previousRun);
    const { queryClient } = renderPanel();
    await waitFor(() => expect(screen.getByTestId("sync-counters")).toHaveTextContent("25 / 25 matches"));

    vi.mocked(api.syncStatus).mockReturnValueOnce(delayedPoll.promise);
    let refresh!: Promise<void>;
    await act(async () => {
      refresh = queryClient.invalidateQueries({ queryKey: ["sync-status"] });
      await Promise.resolve();
    });
    await waitFor(() => expect(api.syncStatus).toHaveBeenCalledTimes(2));

    vi.mocked(api.startSync).mockResolvedValueOnce(nextRun);
    fireEvent.click(screen.getByTestId("start-sync"));
    await waitFor(() => expect(api.startSync).toHaveBeenCalledTimes(1));
    await waitFor(() => expect(screen.getByTestId("sync-counters")).toHaveTextContent("0 / 25 matches"));
    expect(screen.getByTestId("sync-current")).toHaveTextContent("EUW1_2");

    delayedPoll.resolve({ ...running, downloaded: 20, current_match_id: "EUW1_1" });
    await act(async () => {
      await delayedPoll.promise;
      await refresh;
    });
    expect(screen.getByTestId("sync-counters")).toHaveTextContent("0 / 25 matches");
    expect(screen.getByTestId("sync-current")).toHaveTextContent("EUW1_2");
  });
  it("does not let an in-flight poll repopulate the cache after unmount", async () => {
    const oldPoll = deferred<typeof running>();
    vi.mocked(api.syncStatus).mockReturnValueOnce(oldPoll.promise);
    const { queryClient, unmount } = renderPanel();
    await waitFor(() => expect(api.syncStatus).toHaveBeenCalledTimes(1));

    unmount();
    oldPoll.resolve(running);
    await act(async () => {
      await oldPoll.promise;
    });

    expect(queryClient.getQueryData(["sync-status", ownerContext.owner_key, ownerContext.generation])).toBeUndefined();

    vi.mocked(api.syncStatus).mockResolvedValueOnce(idle);
    renderPanel(queryClient);
    expect(screen.queryByTestId("sync-current")).toBeNull();
    await waitFor(() => expect(screen.getByTestId("sync-counters")).toHaveTextContent("0 / 0 matches"));
  });
  it("does not let a delayed running poll undo a newer cancel acknowledgement", async () => {
    const delayedPoll = deferred<typeof running>();
    const cancelled = {
      ...running,
      state: "cancelled" as const,
      downloaded: 7,
      current_match_id: null,
    };
    vi.mocked(api.syncStatus).mockResolvedValueOnce(running);
    const { queryClient } = renderPanel();
    await waitFor(() => expect(screen.getByTestId("sync-counters")).toHaveTextContent("5 / 25 matches"));

    vi.mocked(api.syncStatus).mockReturnValueOnce(delayedPoll.promise);
    let refresh!: Promise<void>;
    await act(async () => {
      refresh = queryClient.invalidateQueries({ queryKey: ["sync-status"] });
      await Promise.resolve();
    });
    await waitFor(() => expect(api.syncStatus).toHaveBeenCalledTimes(2));

    vi.mocked(api.cancelSync).mockResolvedValueOnce(cancelled);
    fireEvent.click(screen.getByTestId("cancel-sync"));
    await waitFor(() => expect(screen.getByText(/queue resumes next session/)).toBeInTheDocument());

    delayedPoll.resolve({ ...running, downloaded: 6 });
    await act(async () => {
      await delayedPoll.promise;
      await refresh;
    });
    expect(screen.getByTestId("sync-counters")).toHaveTextContent("7 / 25 matches");
    expect(screen.getByTestId("cancel-sync")).toBeDisabled();
  });

  it("cancels a running sync via the API", async () => {
    vi.mocked(api.startSync).mockResolvedValue(running);
    vi.mocked(api.cancelSync).mockResolvedValue({ ...running, state: "cancelled", current_match_id: null });
    renderPanel();

    await waitFor(() => expect(screen.getByTestId("start-sync")).not.toBeDisabled());
    fireEvent.click(screen.getByTestId("start-sync"));
    await waitFor(() => expect(screen.getByTestId("cancel-sync")).not.toBeDisabled());

    fireEvent.click(screen.getByTestId("cancel-sync"));
    await waitFor(() => expect(api.cancelSync).toHaveBeenCalledTimes(1));
    expect(await screen.findByText(/queue resumes next session/)).toBeInTheDocument();
  });
});
