import { act, cleanup, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { parseSseMessage, useEvents, type SseMessage } from "./sse";

const urls = vi.hoisted(() => ({
  eventsUrl: vi.fn(async () => "http://sidecar/events"),
  invalidateConnection: vi.fn(),
}));
vi.mock("./client", () => ({
  eventsUrl: urls.eventsUrl,
  invalidateConnection: urls.invalidateConnection,
}));

class FakeEventSource {
  static instances: FakeEventSource[] = [];
  onopen: (() => void) | null = null;
  onmessage: ((event: MessageEvent<string>) => void) | null = null;
  onerror: (() => void) | null = null;
  readyState = 0;
  close = vi.fn(() => {
    this.readyState = 2;
  });

  constructor(readonly url: string) {
    FakeEventSource.instances.push(this);
  }

  open() {
    this.readyState = 1;
    this.onopen?.();
  }

  message(payload: unknown) {
    this.onmessage?.({ data: JSON.stringify(payload) } as MessageEvent<string>);
  }

  error() {
    this.onerror?.();
  }
}

function StatusAndConsumer({ onMessage }: { onMessage: (message: SseMessage) => void }) {
  const connected = useEvents(onMessage);
  return <output data-testid="status">{connected ? "connected" : "offline"}</output>;
}

function StatusOnly() {
  const connected = useEvents();
  return <output data-testid="status-only">{connected ? "connected" : "offline"}</output>;
}

function ConnectionObserver({ onChange }: { onChange: (connected: boolean) => void }) {
  useEvents(undefined, { onConnectionChange: onChange });
  return null;
}

const validSyncProgress = {
  type: "sync.progress",
  ts: "2026-08-24T00:00:00Z",
  data: {
    state: "running",
    mode: "era_first",
    total_queued: 2,
    downloaded: 1,
    skipped: 0,
    failed: 0,
    current_match_id: "NA1_1",
    started_at: "2026-08-24T00:00:00Z",
  },
};

const validChampSelect = {
  type: "champselect.state",
  ts: "2026-08-24T00:00:00Z",
  data: {
    active: true,
    phase: "ChampSelect",
    timer_sec: 23,
    local_assigned_role: "TOP",
    bans_ally: [{ champion_id: 25, champion: "Miss Fortune" }],
    bans_enemy: [{ champion_id: 412, champion: null }],
    ally: [
      {
        cell_id: 0,
        champion_id: 1,
        champion: "Annie",
        name: "Local",
        is_local: true,
        state: "locked",
      },
    ],
    enemy: [
      {
        cell_id: 5,
        champion_id: 238,
        champion: null,
        name: null,
        state: "none",
      },
    ],
  },
};


describe("shared SSE owner", () => {
  beforeEach(() => {
    vi.stubGlobal("EventSource", FakeEventSource);
    FakeEventSource.instances = [];
    urls.eventsUrl.mockClear();
    urls.invalidateConnection.mockClear();
  });

  afterEach(() => {
    cleanup();
    vi.useRealTimers();
  });

  it("validates envelopes and narrows payloads before notifying subscribers", () => {
    const valid = parseSseMessage(validSyncProgress);
    expect(valid?.type).toBe("sync.progress");
    if (valid?.type === "sync.progress") expect(valid.data.downloaded).toBe(1);

    expect(parseSseMessage({ ...validSyncProgress, data: { nope: true } })).toBeNull();
    expect(parseSseMessage({ type: "live.state", ts: "now", data: { active: true } })).toBeNull();
    expect(parseSseMessage({ type: "unknown", ts: "now", data: {} })).toBeNull();
  });
  it("shares strict champ-select validation with REST", () => {
    expect(parseSseMessage(validChampSelect)?.type).toBe("champselect.state");
    for (const data of [
      { ...validChampSelect.data, phase: "InvalidPhase" },
      { ...validChampSelect.data, local_assigned_role: "UNKNOWN" },
      { ...validChampSelect.data, local_assigned_role: 42 },
      { ...validChampSelect.data, enemy: [{ ...validChampSelect.data.enemy[0], name: "Enemy" }] },
      { ...validChampSelect.data, ally: [{ ...validChampSelect.data.ally[0], cell_id: "0" }] },
      { ...validChampSelect.data, ally: [{ ...validChampSelect.data.ally[0], state: "picked-up" }] },
      { ...validChampSelect.data, bans_ally: [{ champion_id: 25, name: "Miss Fortune" }] },
      { ...validChampSelect.data, bans_enemy: [{ champion_id: 25, champion: 42 }] },
      { ...validChampSelect.data, bans_enemy: [{ champion_id: 25, champion: null, name: "obsolete" }] },
    ]) {
      expect(parseSseMessage({ ...validChampSelect, data })).toBeNull();
    }
    const { local_assigned_role: _role, ...oldData } = validChampSelect.data;
    expect(parseSseMessage({ ...validChampSelect, data: oldData })).toBeNull();
    expect(
      parseSseMessage({
        ...validChampSelect,
        data: { ...validChampSelect.data, bans_ally: [{ champion_id: 25, champion: null }] },
      })?.type,
    ).toBe("champselect.state");
  });

  it("retains valid pack.updated versions and rejects malformed version fields", () => {
    const valid = parseSseMessage({
      type: "pack.updated",
      ts: "2026-08-24T00:00:00Z",
      data: { schema_version: 1, pack_version: "v2" },
    });
    expect(valid).toEqual({
      type: "pack.updated",
      ts: "2026-08-24T00:00:00Z",
      data: { schema_version: 1, pack_version: "v2" },
    });

    for (const data of [
      { schema_version: 1 },
      { schema_version: 1, pack_version: "" },
      { schema_version: 1, pack_version: "   " },
      { schema_version: 1, pack_version: 42 },
      { schema_version: 1.5, pack_version: "v2" },
      { schema_version: Number.NaN, pack_version: "v2" },
      { schema_version: Number.POSITIVE_INFINITY, pack_version: "v2" },
    ]) {
      expect(parseSseMessage({ type: "pack.updated", ts: "now", data })).toBeNull();
    }

    expect(
      parseSseMessage({
        type: "hello",
        ts: "now",
        data: { app_version: "dev", pack_version: null },
      }),
    ).toEqual({
      type: "hello",
      ts: "now",
      data: { app_version: "dev", pack_version: null },
    });
  });

  it("opens one source for multiple subscribers and fans out validated events", async () => {
    const received: SseMessage[] = [];
    render(
      <>
        <StatusAndConsumer onMessage={(message) => received.push(message)} />
        <StatusOnly />
      </>,
    );

    await act(async () => {});
    expect(FakeEventSource.instances).toHaveLength(1);
    const source = FakeEventSource.instances[0];
    await act(async () => {
      source.open();
      source.message(validSyncProgress);
      source.message(validChampSelect);
      source.message({
        ...validChampSelect,
        data: { ...validChampSelect.data, bans_ally: [{ champion_id: 25, name: "obsolete" }] },
      });
      source.message({ ...validSyncProgress, data: { invalid: true } });
    });
    expect(screen.getByTestId("status")).toHaveTextContent("connected");
    expect(screen.getByTestId("status-only")).toHaveTextContent("connected");
    expect(received).toHaveLength(2);
    expect(received.map((message) => message.type)).toEqual(["sync.progress", "champselect.state"]);
  });

  it("notifies connection edges while retaining one shared source across reconnect", async () => {
    vi.useFakeTimers();
    const firstEdges: boolean[] = [];
    const secondEdges: boolean[] = [];
    render(
      <>
        <ConnectionObserver onChange={(connected) => firstEdges.push(connected)} />
        <ConnectionObserver onChange={(connected) => secondEdges.push(connected)} />
      </>,
    );

    await act(async () => {});
    expect(FakeEventSource.instances).toHaveLength(1);
    await act(async () => {
      FakeEventSource.instances[0].open();
    });
    expect(firstEdges).toEqual([false, true]);
    expect(secondEdges).toEqual([false, true]);

    await act(async () => {
      FakeEventSource.instances[0].error();
      vi.advanceTimersByTime(2_000);
    });
    await act(async () => {});
    expect(FakeEventSource.instances).toHaveLength(2);
    await act(async () => {
      FakeEventSource.instances[1].open();
    });
    expect(firstEdges).toEqual([false, true, false, true]);
    expect(secondEdges).toEqual([false, true, false, true]);
  });

  it("retains one shared live owner and fan-out across reconnect with mixed subscribers", async () => {
    vi.useFakeTimers();
    const received: SseMessage[] = [];
    const edges: boolean[] = [];
    render(
      <>
        <StatusAndConsumer onMessage={(message) => received.push(message)} />
        <StatusOnly />
        <ConnectionObserver onChange={(connected) => edges.push(connected)} />
      </>,
    );

    await act(async () => {});
    expect(FakeEventSource.instances).toHaveLength(1);
    expect(edges).toEqual([false]);
    await act(async () => {
      FakeEventSource.instances[0].open();
    });
    expect(edges).toEqual([false, true]);

    await act(async () => {
      FakeEventSource.instances[0].error();
      vi.advanceTimersByTime(2_000);
      await Promise.resolve();
    });
    expect(FakeEventSource.instances).toHaveLength(2);
    expect(FakeEventSource.instances[0].close).toHaveBeenCalled();

    await act(async () => {
      FakeEventSource.instances[1].open();
      FakeEventSource.instances[1].message(validSyncProgress);
    });

    // Exactly one non-closed owner remains and frames still fan out to the
    // message subscriber through the reconnected shared source.
    expect(FakeEventSource.instances.filter((instance) => instance.readyState !== 2)).toHaveLength(1);
    expect(received.map((message) => message.type)).toEqual(["sync.progress"]);
    expect(edges).toEqual([false, true, false, true]);
  });

  it("closes the source and cancels reconnect when the final subscriber unmounts", async () => {
    vi.useFakeTimers();
    const view = render(<StatusOnly />);
    await act(async () => {});
    const source = FakeEventSource.instances[0];
    source.error();
    view.unmount();
    await act(async () => {
      vi.advanceTimersByTime(10_000);
    });
    expect(urls.invalidateConnection).toHaveBeenCalledOnce();
    expect(source.close).toHaveBeenCalled();
    expect(FakeEventSource.instances).toHaveLength(1);
  });
});
