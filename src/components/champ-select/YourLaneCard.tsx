// v1 has no live lane opponent, so the design's Syndra content becomes an idle
// state that keeps the card's gradient and avatar-tile styling.
export function YourLaneCard() {
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
        <span className="pill" style={{ background: "var(--color-danger-low)", color: "#f4c3ce" }}>
          <span style={{ width: 6, height: 6, borderRadius: 999, background: "var(--color-amber)" }} />
          Your lane
        </span>
        <span className="mono-n" style={{ fontSize: 10, color: "var(--color-dimmer)" }}>
          no live opponent
        </span>
      </div>
      <div style={{ display: "flex", alignItems: "center", gap: 11 }}>
        <div
          style={{
            width: 50,
            height: 50,
            flex: "none",
            borderRadius: 16,
            background: "linear-gradient(150deg,var(--color-danger),#6d2b3e)",
            display: "grid",
            placeItems: "center",
            font: "700 15px var(--font-mono)",
            color: "#2c1520",
            boxShadow: "0 4px 0 rgba(0,0,0,.5),0 14px 26px -8px rgba(229,115,143,.55)",
            opacity: 0.75,
          }}
        >
          ?
        </div>
        <div style={{ flex: 1 }}>
          <div style={{ font: "700 14px var(--font-mono)", letterSpacing: "-.02em" }}>
            Lock in to see your lane matchup
          </div>
          <div style={{ fontSize: 10, color: "var(--color-dim)", marginTop: 3 }}>
            Opponent intel arrives with the live session.
          </div>
        </div>
      </div>
    </div>
  );
}
