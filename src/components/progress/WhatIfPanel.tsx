const SLIDERS = [
  { key: "gold10", label: "Gold@10" },
  { key: "plates14", label: "Plates by 14" },
  { key: "safe-recalls", label: "Safe recalls" },
];

export function WhatIfPanel() {
  return (
    <div
      className="card3b"
      data-testid="what-if-panel"
      style={{ padding: 13, display: "flex", flexDirection: "column", gap: 8 }}
    >
      <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
        <span
          style={{
            width: 6,
            height: 6,
            borderRadius: 999,
            background: "var(--color-info)",
            flex: "none",
          }}
        />
        <span
          style={{
            font: "700 9.5px var(--font-mono)",
            letterSpacing: ".11em",
            color: "var(--color-dim)",
          }}
        >
          WHAT-IF SIMULATOR · UNAVAILABLE
        </span>
      </div>
      {SLIDERS.map((s) => (
        <div key={s.key}>
          <div
            style={{
              display: "flex",
              justifyContent: "space-between",
              fontSize: 9.5,
              marginBottom: 3,
            }}
          >
            <span style={{ color: "var(--color-dim)" }}>{s.label}</span>
            <span className="mono-n">Unavailable</span>
          </div>
          <div
            aria-label={`${s.label} unavailable until the Honest Model ships`}
            data-testid={`what-if-track-${s.key}`}
            style={{
              position: "relative",
              height: 6,
              borderRadius: 999,
              background: "var(--color-deep)",
              overflow: "hidden",
            }}
          />
        </div>
      ))}
      <div
        style={{
          marginTop: "auto",
          padding: "9px 10px",
          borderRadius: 12,
          background: "var(--color-accent-low)",
          boxShadow: "var(--shadow-z1)",
        }}
      >
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "baseline" }}>
          <span style={{ fontSize: 9.5, color: "#e7e5fe" }}>Predicted win rate</span>
          <span
            className="mono-n"
            data-testid="what-if-prediction"
            style={{ font: "700 16px var(--font-mono)", color: "#e7e5fe" }}
          >
            Unavailable
          </span>
        </div>
      </div>
      <p
        style={{ margin: 0, fontSize: 8.5, lineHeight: 1.4, color: "var(--color-dimmer)" }}
        data-testid="what-if-caption"
      >
        Honest Model unavailable; personal estimates withheld until it ships (ADR-0003).
      </p>
    </div>
  );
}
