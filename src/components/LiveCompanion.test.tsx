import { fireEvent, render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { champSelectSession } from "../routes/__tests__/fixtures";
import type { LiveStatus } from "../api/types";

const mocks = vi.hoisted(() => ({ invoke: vi.fn(), useLiveStatus: vi.fn() }));
vi.mock("@tauri-apps/api/core", () => ({ invoke: mocks.invoke }));
vi.mock("../api/hooks", () => ({ useLiveStatus: mocks.useLiveStatus }));
const { invoke } = mocks;

const idleStatus: LiveStatus = {
  champ_select: { active: false, phase: null },
  ingame: { active: false, game_id: null, mode: null, clock_s: 0 },
  last_error: null,
};
const champSelectStatus: LiveStatus = {
  ...idleStatus,
  champ_select: { active: true, phase: champSelectSession.phase },
};
const inGameStatus: LiveStatus = {
  ...idleStatus,
  ingame: { active: true, game_id: 42, mode: "CLASSIC", clock_s: 3 },
};

import { LiveCompanion } from "./LiveCompanion";

describe("LiveCompanion", () => {
  let liveStatusData: LiveStatus | undefined;

  beforeEach(() => {
    invoke.mockReset();
    invoke.mockResolvedValue(undefined);
    liveStatusData = undefined;
    mocks.useLiveStatus.mockReset();
    mocks.useLiveStatus.mockImplementation(() => ({ data: liveStatusData }));
  });

  it("applies unified status hydration and arbitration precedence through one Tauri bridge", async () => {
    const view = render(<LiveCompanion />);
    liveStatusData = champSelectStatus;
    view.rerender(<LiveCompanion />);
    expect(await screen.findByTestId("live-companion-mode")).toHaveTextContent("champ select");
    expect(invoke).toHaveBeenLastCalledWith("set_live_companion_mode", {
      mode: "champ-select",
    });

    liveStatusData = { ...inGameStatus, champ_select: champSelectStatus.champ_select };
    view.rerender(<LiveCompanion />);
    expect(await screen.findByTestId("live-companion-mode")).toHaveTextContent("in-game");
    expect(invoke).toHaveBeenLastCalledWith("set_live_companion_mode", {
      mode: "in-game",
      expanded: false,
    });

    liveStatusData = idleStatus;
    view.rerender(<LiveCompanion />);
    expect(await screen.findByTestId("live-companion-mode")).toHaveTextContent("idle");
    expect(invoke).toHaveBeenLastCalledWith("set_live_companion_mode", { mode: "idle" });
  });

  it("hydrates in-game from the first successful status query collapsed", async () => {
    liveStatusData = inGameStatus;
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

  it("keeps expansion across status refreshes and resets after confirmed departure", async () => {
    liveStatusData = inGameStatus;
    const view = render(<LiveCompanion />);
    const toggle = await screen.findByRole("button", { name: "Expand Live Companion" });
    toggle.focus();
    fireEvent.keyDown(toggle, { key: "Enter", code: "Enter" });
    fireEvent.click(toggle);
    expect(toggle).toHaveAccessibleName("Collapse Live Companion");
    expect(toggle).toHaveAttribute("aria-expanded", "true");

    liveStatusData = { ...inGameStatus, ingame: { ...inGameStatus.ingame, clock_s: 9 } };
    view.rerender(<LiveCompanion />);
    expect(await screen.findByRole("button", { name: "Collapse Live Companion" })).toHaveAttribute(
      "aria-expanded",
      "true",
    );

    liveStatusData = idleStatus;
    view.rerender(<LiveCompanion />);
    expect(await screen.findByTestId("live-companion-mode")).toHaveTextContent("idle");
    liveStatusData = inGameStatus;
    view.rerender(<LiveCompanion />);
    const resetToggle = await screen.findByRole("button", { name: "Expand Live Companion" });
    expect(resetToggle).toHaveAttribute("aria-expanded", "false");
  });
});
