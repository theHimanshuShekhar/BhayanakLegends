import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { PlayerList } from "./PlayerList";
import { idleIngame } from "../../routes/__tests__/fixtures";

describe("PlayerList loading semantics", () => {
  it("marks a pending roster request busy, then announces settled idle without a loading skeleton", () => {
    const { rerender } = render(<PlayerList snapshot={undefined} loading />);
    expect(screen.getByTestId("player-list")).toHaveAttribute("aria-busy", "true");
    rerender(<PlayerList snapshot={idleIngame} loading={false} />);
    expect(screen.getByTestId("player-list")).toHaveAttribute("aria-busy", "false");
    expect(screen.getByText("Waiting for an active game")).toBeVisible();
    expect(document.querySelector(".live-skeleton")).toBeNull();
  });
});
