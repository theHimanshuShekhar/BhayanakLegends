import { Dot } from "./bits";

const SKELETON_ROWS = 3;

function DashCell() {
  return (
    <div
      style={{
        flex: 1,
        padding: "7px 8px",
        borderRadius: 13,
        background: "var(--color-surface-3)",
        boxShadow: "var(--shadow-z1)",
        display: "flex",
        justifyContent: "space-between",
        alignItems: "center",
      }}
    >
      {["—", "—", "—", "—"].map((d, i) => (
        <span key={i} className="mono-n" style={{ fontSize: 9, color: "var(--color-dimmer)" }}>
          {d}
        </span>
      ))}
    </div>
  );
}

function SkeletonSide() {
  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
      {Array.from({ length: SKELETON_ROWS }, (_, row) => (
        <div key={row} style={{ display: "flex", gap: 6 }}>
          {Array.from({ length: 5 }, (_, cell) => (
            <DashCell key={cell} />
          ))}
        </div>
      ))}
    </div>
  );
}

/**
 * Player-list chrome from the design. Real rosters only exist once the Live
 * Client Data API is reachable, so until then the rows are dash placeholders —
 * no names, nothing that could be mistaken for a real player.
 */
export function PlayerList({ active }: { active: boolean }) {
  return (
    <section
      className="card3b"
      data-testid="player-list"
      style={{
        flex: "none",
        padding: "11px 13px",
        background: "linear-gradient(180deg,var(--color-surface-2),var(--color-surface))",
      }}
    >
      <div style={{ display: "flex", alignItems: "center", gap: 9, marginBottom: 9 }}>
        <Dot color="var(--color-teal)" />
        <span
          style={{
            font: "700 9.5px var(--font-mono)",
            letterSpacing: ".13em",
            color: "var(--color-dim)",
          }}
        >
          PLAYER LIST · LEVEL · K/D/A · CS · WARD SCORE
        </span>
        <span
          className="mono-n"
          data-testid="score-strip"
          style={{ marginLeft: "auto", fontSize: 10, color: "var(--color-dimmer)" }}
        >
          — kills · — turrets
        </span>
      </div>
      {!active && (
        <div style={{ display: "flex", justifyContent: "center", marginBottom: 9 }}>
          <span
            className="pill"
            data-testid="waiting-pill"
            style={{ background: "var(--color-amber-low)", color: "var(--color-amber)" }}
          >
            waiting for :2999
          </span>
        </div>
      )}
      <div style={{ display: "grid", gridTemplateColumns: "1fr 1px 1fr", gap: 13 }}>
        <SkeletonSide />
        <div style={{ background: "linear-gradient(180deg,transparent,var(--color-line),transparent)" }} />
        <SkeletonSide />
      </div>
    </section>
  );
}
