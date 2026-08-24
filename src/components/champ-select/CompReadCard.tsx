// The design drives the damage-mix bar from live comp data; no damage-fit
// finding exists in the pack and there is no live session at v1, so the bar
// stays neutral with an honest caption.
export function CompReadCard() {
  return (
    <div className="card3" data-testid="card-comp-read" style={{ padding: 12, display: "flex", flexDirection: "column", gap: 9 }}>
      <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
        <span style={{ width: 6, height: 6, borderRadius: 999, background: "#7a8098" }} />
        <span style={{ font: "700 9.5px var(--font-mono)", letterSpacing: ".11em", color: "var(--color-dim)" }}>
          COMP READ
        </span>
        <span
          className="pill"
          style={{ marginLeft: "auto", background: "var(--color-surface-3)", color: "var(--color-dim)" }}
        >
          Idle
        </span>
      </div>
      <div>
        <div style={{ display: "flex", justifyContent: "space-between", fontSize: 9.5, color: "var(--color-dim)", marginBottom: 4 }}>
          <span>Damage mix</span>
          <span className="mono-n">— / —</span>
        </div>
        <div
          style={{
            height: 7,
            borderRadius: 999,
            overflow: "hidden",
            display: "flex",
            background: "var(--color-deep)",
            boxShadow: "inset 0 2px 4px rgba(0,0,0,.7)",
          }}
        />
      </div>
      <p style={{ margin: "auto 0 0", fontSize: 10, lineHeight: 1.5, color: "#cfd3e5" }}>
        Comp read arrives with the live session.
      </p>
    </div>
  );
}
