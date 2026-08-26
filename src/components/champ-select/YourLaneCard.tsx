import type { AssignedRole, CellState } from "../../api/types";
import { initials } from "./shared";

// Lane-opponent intel stays out of scope (and enemy-name-free). This card
// distinguishes a local intent from completed lock evidence.
export function YourLaneCard({
  champion,
  tier,
  role = null,
  state = "none",
  locked = false,
}: {
  champion?: string | null;
  tier?: string | null;
  role?: AssignedRole | null;
  state?: CellState;
  locked?: boolean;
}) {
  const hasChampion = !!champion;
  const status = locked
    ? role
      ? `LOCKED · ${role}`
      : "LOCKED IN"
    : hasChampion
      ? `${state === "intent" ? "INTENT" : state === "hover" ? "HOVER" : "PICKED"} · NOT LOCKED`
      : role
        ? `${role} · AWAITING PICK`
        : "AWAITING ROLE";

  return (
    <div
      className="card3b"
      data-testid="card-your-lane"
      style={{
        padding: 13,
        background: "linear-gradient(165deg,#2d1c28,var(--color-surface-2) 62%)",
        boxShadow:
          "0 4px 0 rgba(0,0,0,.55),0 26px 44px -16px rgba(0,0,0,.9),inset 0 1px 0 rgba(255,255,255,.08)",
      }}
    >
      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: 10 }}>
        <span className="pill" style={{ background: locked ? "var(--color-teal-low)" : "var(--color-danger-low)", color: locked ? "var(--color-teal)" : "#f4c3ce" }}>
          <span style={{ width: 6, height: 6, borderRadius: 999, background: locked ? "var(--color-teal)" : "var(--color-amber)" }} />
          Your lane
        </span>
        <span
          className="pill mono-n"
          data-testid="your-lane-tier"
          style={{ fontSize: 9, background: locked && tier ? "var(--color-teal-low)" : "var(--color-surface-3)", color: locked && tier ? "var(--color-teal)" : "var(--color-dim)" }}
        >
          {locked && tier ? `FINDINGS PACK · TIER ${tier}` : status}
        </span>
      </div>
      <div style={{ display: "flex", alignItems: "center", gap: 11 }}>
        <div
          style={{
            width: 50,
            height: 50,
            flex: "none",
            borderRadius: 16,
            background: hasChampion ? "linear-gradient(150deg,var(--color-accent),#3b2a75)" : "linear-gradient(150deg,var(--color-danger),#6d2b3e)",
            display: "grid",
            placeItems: "center",
            font: "700 15px var(--font-mono)",
            color: hasChampion ? "#efeaff" : "#2c1520",
            boxShadow: "0 4px 0 rgba(0,0,0,.5),0 14px 26px -8px rgba(122,97,255,.5)",
            opacity: hasChampion ? 1 : 0.75,
          }}
        >
          {hasChampion ? initials(champion) : "?"}
        </div>
        <div style={{ flex: 1 }}>
          <div data-testid="your-lane-champion" style={{ font: "700 14px var(--font-mono)", letterSpacing: "-.02em" }}>
            {hasChampion ? champion : locked ? "Champion unavailable" : "Choose your champion"}
          </div>
          <div style={{ fontSize: 10, color: "var(--color-dim)", marginTop: 3 }}>
            {locked
              ? "Locked in — lane matchup intel loads with the game."
              : hasChampion
                ? "Selection is visible, but completion is not confirmed."
                : "Pick intent and role evidence remain visible until lock."}
          </div>
        </div>
      </div>
    </div>
  );
}
