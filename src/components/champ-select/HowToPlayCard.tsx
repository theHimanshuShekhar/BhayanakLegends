// Gameplan pills are champion-specific; with no locked pick at v1 the card
// keeps the design structure in an idle state instead of inventing guidance.
export function HowToPlayCard() {
  return (
    <div
      className="card3"
      data-testid="card-how-to-play"
      style={{ padding: 12, flex: 1, minHeight: 0, display: "flex", flexDirection: "column", gap: 8 }}
    >
      <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
        <span style={{ width: 6, height: 6, borderRadius: 999, background: "#7a8098" }} />
        <span style={{ font: "700 9.5px var(--font-mono)", letterSpacing: ".11em", color: "var(--color-dim)" }}>
          HOW TO PLAY IT
        </span>
      </div>
      <div
        style={{
          display: "flex",
          gap: 9,
          padding: 9,
          borderRadius: 13,
          background: "var(--color-surface-2)",
          boxShadow: "var(--shadow-z1)",
        }}
      >
        <span
          className="pill"
          style={{ alignSelf: "flex-start", background: "var(--color-surface-3)", color: "var(--color-dim)" }}
        >
          Idle
        </span>
        <p style={{ margin: 0, fontSize: 11, lineHeight: 1.5, color: "#cfd3e5" }}>
          Lock a champion and the early / mid / late gameplan pills arrive with the live session.
        </p>
      </div>
      <div
        style={{
          marginTop: "auto",
          display: "flex",
          alignItems: "center",
          gap: 9,
          padding: "9px 10px",
          borderRadius: 13,
          background: "var(--color-surface-2)",
          boxShadow: "var(--shadow-z1)",
        }}
      >
        <span style={{ width: 6, height: 6, borderRadius: 999, background: "var(--color-dimmer)", flex: "none" }} />
        <div style={{ fontSize: 9.5, lineHeight: 1.4, color: "var(--color-dim)" }}>
          Gameplan guidance is champion-specific — it needs a locked pick, not pack averages.
        </div>
      </div>
    </div>
  );
}
