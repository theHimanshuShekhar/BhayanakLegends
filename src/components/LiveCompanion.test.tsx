import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { champSelectSession, ingameSnapshot, idleSession } from "../routes/__tests__/fixtures";
import type { LiveStatus } from "../api/types";
import type { SseMessage } from "../api/sse";

const mocks = vi.hoisted(() => ({ invoke: vi.fn(), useLiveStatus: vi.fn() }));
vi.mock("@tauri-apps/api/core", () => ({ invoke: mocks.invoke }));
vi.mock("../api/hooks", () => ({ useLiveStatus: mocks.useLiveStatus }));
const { invoke } = mocks;
let pushSse: ((message: SseMessage) => void) | undefined;
vi.mock("../api/sse", () => ({
  useEvents: (onMessage?: (message: SseMessage) => void) => {
    pushSse = onMessage;
    return true;
  },
}));

const idleStatus: LiveStatus = {
  champ_select: { active: false, phase: null },
  ingame: { active: false, game_id: null, mode: null, clock_s: 0 },
  last_error: null,
};
const inGameStatus: LiveStatus = {
  ...idleStatus,
  ingame: { active: true, game_id: 42, mode: "CLASSIC", clock_s: 3 },
};

import { LiveCompanion } from "./LiveCompanion";

describe("LiveCompanion", () => {
  beforeEach(() => {
    invoke.mockReset();
    invoke.mockResolvedValue(undefined);
    mocks.useLiveStatus.mockReset();
    mocks.useLiveStatus.mockReturnValue({ data: undefined });
    pushSse = undefined;
  });

  it("replays idle, champ select, in-game, and idle through one Tauri bridge", async () => {
    render(<LiveCompanion />);
    await waitFor(() => expect(pushSse).toBeDefined());

    pushSse!({ type: "champselect.state", ts: "1", data: champSelectSession });
    expect(await screen.findByTestId("live-companion-mode")).toHaveTextContent("champ select");
    expect(invoke).toHaveBeenLastCalledWith("set_live_companion_mode", {
      mode: "champ-select",
    });

    pushSse!({ type: "live.state", ts: "2", data: ingameSnapshot });
    expect(await screen.findByTestId("live-companion-mode")).toHaveTextContent("in-game");
    expect(invoke).toHaveBeenLastCalledWith("set_live_companion_mode", {
      mode: "in-game",
      expanded: false,
    });

    pushSse!({ type: "live.state", ts: "3", data: { ...ingameSnapshot, active: false } });
    pushSse!({ type: "champselect.state", ts: "4", data: idleSession });
    expect(await screen.findByTestId("live-companion-mode")).toHaveTextContent("idle");
    expect(invoke).toHaveBeenLastCalledWith("set_live_companion_mode", { mode: "idle" });
  });

  it("hydrates in-game from the first successful status query", async () => {
    mocks.useLiveStatus.mockReturnValue({ data: inGameStatus });

    render(<LiveCompanion />);

    expect(await screen.findByTestId("live-companion-mode")).toHaveTextContent("in-game");
    expect(invoke).toHaveBeenLastCalledWith("set_live_companion_mode", {
      mode: "in-game",
      expanded: false,
    });
    expect(
      screen.getByText("Borderless-windowed mode required; this companion is not click-through."),
    ).toBeVisible();
  });

  it("expands and collapses in-game without opening a second event owner", async () => {
    render(<LiveCompanion />);
    await waitFor(() => expect(pushSse).toBeDefined());
    pushSse!({ type: "live.state", ts: "1", data: ingameSnapshot });

    const toggle = await screen.findByRole("button", { name: "Expand Live Companion" });
    toggle.focus();
    fireEvent.keyDown(toggle, { key: "Enter", code: "Enter" });
    fireEvent.click(toggle);
    expect(invoke).toHaveBeenLastCalledWith("set_live_companion_mode", {
      mode: "in-game",
      expanded: true,
    });
    expect(toggle).toHaveAccessibleName("Collapse Live Companion");
    expect(toggle).toHaveAttribute("aria-expanded", "true");
    expect(toggle).toHaveFocus();

    fireEvent.keyDown(toggle, { key: " ", code: "Space" });
    fireEvent.click(toggle);
    expect(invoke).toHaveBeenLastCalledWith("set_live_companion_mode", {
      mode: "in-game",
      expanded: false,
    });
    expect(toggle).toHaveAccessibleName("Expand Live Companion");
    expect(toggle).toHaveAttribute("aria-expanded", "false");
    expect(toggle).toHaveFocus();
  });
});
