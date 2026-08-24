import { act, cleanup, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { parseSseMessage, useEvents, type SseMessage } from "./sse";

const urls = vi.hoisted(() => ({ eventsUrl: vi.fn(async () => "http://sidecar/events") }));
vi.mock("./client", () => ({ eventsUrl: urls.eventsUrl }));

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

describe("shared SSE owner", () => {
  beforeEach(() => {
    vi.stubGlobal("EventSource", FakeEventSource);
    FakeEventSource.instances = [];
    urls.eventsUrl.mockClear();
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
      source.message({ ...validSyncProgress, data: { invalid: true } });
    });
    expect(screen.getByTestId("status")).toHaveTextContent("connected");
    expect(screen.getByTestId("status-only")).toHaveTextContent("connected");
    expect(received).toHaveLength(1);
    expect(received[0].type).toBe("sync.progress");
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
    expect(source.close).toHaveBeenCalled();
    expect(FakeEventSource.instances).toHaveLength(1);
  });
});
