import type { ChampSelectAllyCell, ChampSelectSnapshot } from "../../api/types";
import { championLabel, STATE_CAPTION } from "./BanStrip";
import { initials } from "./shared";

// Teammate champions come from the live LCU session (GET /live/session).
// Enemy rosters are champion-level only by policy — see BanStrip.
export function YourSideCard({ session }: { session: ChampSelectSnapshot | undefined }) {
  const active = !!session?.active;
  const cells: ChampSelectAllyCell[] = (session?.ally ?? []).slice(0, 5);
  const rows: (ChampSelectAllyCell | null)[] = active ? cells : [null, null, null];
  return (
    <div className="card3" data-testid="cs-your-side" style={{ padding: 12, display: "flex", flexDirection: "column", gap: 8 }}>
      <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
        <span style={{ width: 6, height: 6, borderRadius: 999, background: "var(--color-amber)" }} />
        <span style={{ font: "700 9.5px var(--font-mono)", letterSpacing: ".11em", color: "var(--color-dim)" }}>
          YOUR SIDE · RANKED
        </span>
      </div>
      {rows.map((cell, i) =>
        cell ? (
          <div
            key={cell.cell_id}
            data-testid={`cs-side-slot-${i}`}
            style={{ display: "flex", alignItems: "center", gap: 9 }}
          >
            <div
              style={{
                width: 24,
                height: 24,
                borderRadius: 8,
                background: "linear-gradient(150deg,#454a66,#22263a)",
                display: "grid",
                placeItems: "center",
                font: "700 8px var(--font-mono)",
                color: "#b2b6ca",
                flex: "none",
              }}
            >
              {initials(championLabel(cell.champion, cell.champion_id))}
            </div>
            <div style={{ flex: 1, fontSize: 10, minWidth: 0 }}>
              {championLabel(cell.champion, cell.champion_id)}
              {cell.name && (
                <span style={{ color: "var(--color-dimmer)" }}> · {cell.name}</span>
              )}
              {cell.is_local && (
                <span
                  className="pill"
                  style={{
                    marginLeft: 6,
                    background: "var(--color-accent)",
                    color: "#0e1020",
                    fontSize: 7.5,
                    padding: "1px 5px",
                  }}
                >
                  YOU
                </span>
              )}
            </div>
            <span
              className="pill"
              style={{ background: "var(--color-surface-3)", color: "var(--color-dim)" }}
            >
              {STATE_CAPTION[cell.state] ?? cell.state}
            </span>
          </div>
        ) : (
          <div key={`idle-${i}`} style={{ display: "flex", alignItems: "center", gap: 9, opacity: 0.6 }}>
            <div
              style={{
                width: 24,
                height: 24,
                borderRadius: 8,
                background: "linear-gradient(150deg,#454a66,#22263a)",
                display: "grid",
                placeItems: "center",
                font: "700 8px var(--font-mono)",
                color: "#b2b6ca",
              }}
            >
              ?
            </div>
            <div style={{ flex: 1, fontSize: 10 }}>—</div>
            <span className="pill" style={{ background: "var(--color-surface-3)", color: "var(--color-dim)" }}>
              —
            </span>
          </div>
        ),
      )}
    </div>
  );
}
