export function LeakPanel() {
  return (
    <div
      data-testid="deaths-panel"
      style={{
        padding: 15,
        borderRadius: 22,
        background: "linear-gradient(160deg,#2d1c28,var(--color-surface) 68%)",
        boxShadow: "var(--shadow-z2)",
        display: "flex",
        flexDirection: "column",
        gap: 10,
        minHeight: 0,
      }}
    >
      <div style={{ display: "flex", alignItems: "center", gap: 9 }}>
        <span className="pill" style={{ background: "var(--color-surface-3)", color: "var(--color-dim)" }}>
          Idle
        </span>
        <span
          style={{
            font: "700 9.5px var(--font-mono)",
            letterSpacing: ".14em",
            color: "var(--color-dim)",
          }}
        >
          DEATHS BY GAME MINUTE
        </span>
        <span className="mono-n" style={{ marginLeft: "auto", fontSize: 10, color: "var(--color-dimmer)" }}>
          no data yet
        </span>
      </div>
      <p
        style={{
          margin: "auto 0 0",
          fontSize: 10.5,
          lineHeight: 1.55,
          color: "var(--color-dim)",
        }}
        data-testid="deaths-idle-caption"
      >
        Deaths-by-minute lands with the loltrends wheel timeline features — sync games from the
        History tab and the leak chart fills this panel.
      </p>
    </div>
  );
}
