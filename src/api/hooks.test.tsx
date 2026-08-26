import { act, cleanup, render, screen, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import {
  champSelectSession,
  idleSession,
  ingameSnapshot,
  champSelectActive,
  ingameActive,
} from "../routes/__tests__/fixtures";
import { useLiveStatus } from "./hooks";
import type { LiveStatus } from "./types";
const mocks = vi.hoisted(() => ({
  liveStatus: vi.fn(),
  eventsUrl: vi.fn(async () => "http://sidecar/events"),
  invalidateConnection: vi.fn(),
}));
vi.mock("./client", () => ({
  api: { liveStatus: mocks.liveStatus },
  eventsUrl: mocks.eventsUrl,
  invalidateConnection: mocks.invalidateConnection,
}));

class FakeEventSource {
  static instances: FakeEventSource[] = [];
  onopen: (() => void) | null = null;
  onmessage: ((event: MessageEvent<string>) => void) | null = null;
  onerror: (() => void) | null = null;
  close = vi.fn();

  constructor(readonly url: string) {
    FakeEventSource.instances.push(this);
  }

  open() {
    this.onopen?.();
  }

  message(payload: unknown) {
    this.onmessage?.({ data: JSON.stringify(payload) } as MessageEvent<string>);
  }

  error() {
    this.onerror?.();
  }
}

const idleStatus: LiveStatus = {
  champ_select: { active: false, phase: null },
  ingame: { active: false, game_id: null, mode: null, clock_s: 0 },
  last_error: null,
};

function deferred<T>() {
  let resolve!: (value: T) => void;
  const promise = new Promise<T>((complete) => {
    resolve = complete;
  });
  return { promise, resolve };
}

function StatusProbe() {
  const query = useLiveStatus();
  return (
    <output data-testid="status">
      {query.data ? `${query.data.champ_select.active},${query.data.ingame.active}` : "pending"}
    </output>
  );
}

function renderProbe(queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } })) {
  return {
    queryClient,
    ...render(
      <QueryClientProvider client={queryClient}>
        <StatusProbe />
      </QueryClientProvider>,
    ),
  };
}

describe("useLiveStatus arbitration", () => {
  beforeEach(() => {
    vi.stubGlobal("EventSource", FakeEventSource);
    FakeEventSource.instances = [];
    mocks.liveStatus.mockReset();
    mocks.eventsUrl.mockClear();
    mocks.invalidateConnection.mockClear();
  });

  afterEach(() => {
    cleanup();
    vi.useRealTimers();
  });

  it("keeps a newer partial frame over an older poll, then accepts a later full poll", async () => {
    const first = deferred<LiveStatus>();
    mocks.liveStatus.mockReturnValueOnce(first.promise);
    const { queryClient } = renderProbe();
    await waitFor(() => expect(mocks.liveStatus).toHaveBeenCalledOnce());
    expect(FakeEventSource.instances).toHaveLength(1);
    await act(async () => FakeEventSource.instances[0].open());

    FakeEventSource.instances[0].message({
      type: "live.state",
      ts: "newer",
      data: { ...ingameSnapshot, active: true },
    });
    first.resolve(idleStatus);
    await act(async () => first.promise);
    await waitFor(() => expect(screen.getByTestId("status")).toHaveTextContent("false,true"));

    mocks.liveStatus.mockResolvedValueOnce({
      ...idleStatus,
      champ_select: { active: true, phase: "ChampSelect" },
    });
    await act(async () => {
      await queryClient.invalidateQueries({ queryKey: ["live-status"] });
    });
    await waitFor(() => expect(screen.getByTestId("status")).toHaveTextContent("true,false"));
  });

  it("keeps a newer champselect.state over an older poll, then lets a later poll reconcile both fields", async () => {
    const first = deferred<LiveStatus>();
    mocks.liveStatus.mockReturnValueOnce(first.promise);
    const { queryClient } = renderProbe();
    await waitFor(() => expect(mocks.liveStatus).toHaveBeenCalledOnce());
    await act(async () => FakeEventSource.instances[0].open());

    FakeEventSource.instances[0].message({
      type: "champselect.state",
      ts: "newer",
      data: champSelectSession,
    });
    first.resolve(idleStatus);
    await act(async () => first.promise);
    await waitFor(() => expect(screen.getByTestId("status")).toHaveTextContent("true,false"));

    // A poll begun after the frame reconciles the full coarse status.
    mocks.liveStatus.mockResolvedValueOnce(ingameActive);
    await act(async () => {
      await queryClient.invalidateQueries({ queryKey: ["live-status"] });
    });
    await waitFor(() => expect(screen.getByTestId("status")).toHaveTextContent("false,true"));
  });

  it("applies partial frames strictly inside their own field", async () => {
    mocks.liveStatus.mockResolvedValueOnce(champSelectActive);
    renderProbe();
    await waitFor(() => expect(screen.getByTestId("status")).toHaveTextContent("true,false"));
    await act(async () => FakeEventSource.instances[0].open());

    // An in-game frame must not disturb the champ-select field; with both
    // flags raised the component derives in-game from this unified state.
    await act(async () => {
      FakeEventSource.instances[0].message({
        type: "live.state",
        ts: "newer",
        data: { ...ingameSnapshot, active: true },
      });
    });
    await waitFor(() => expect(screen.getByTestId("status")).toHaveTextContent("true,true"));

    // A champ-select frame must not disturb the in-game field.
    await act(async () => {
      FakeEventSource.instances[0].message({
        type: "champselect.state",
        ts: "newer",
        data: idleSession,
      });
    });
    await waitFor(() => expect(screen.getByTestId("status")).toHaveTextContent("false,true"));
  });

  it("requests one status refetch on reconnect while sharing one source", async () => {
    mocks.liveStatus.mockResolvedValue(idleStatus);
    vi.useFakeTimers();
    renderProbe();
    await act(async () => {});
    expect(FakeEventSource.instances).toHaveLength(1);
    await act(async () => FakeEventSource.instances[0].open());
    expect(mocks.liveStatus).toHaveBeenCalledTimes(1);

    await act(async () => {
      FakeEventSource.instances[0].error();
      vi.advanceTimersByTime(2_000);
      await Promise.resolve();
    });
    expect(FakeEventSource.instances).toHaveLength(2);
    await act(async () => FakeEventSource.instances[1].open());
    await act(async () => {});
    expect(mocks.liveStatus).toHaveBeenCalledTimes(2);
  });
});
