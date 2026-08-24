const SLIDERS = [
  { key: "gold10", label: "Gold@10", display: "−280g", value: 38, accent: false },
  { key: "plates14", label: "Plates by 14", display: "1 of 6", value: 17, accent: false },
  { key: "safe-recalls", label: "Safe recalls", display: "62%", value: 62, accent: true },
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
          WHAT-IF SIMULATOR
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
            <span className="mono-n">{s.display}</span>
          </div>
          <div
            style={{
              position: "relative",
              height: 6,
              borderRadius: 999,
              background: "var(--color-deep)",
              overflow: "hidden",
            }}
          >
            <div
              style={{
                width: `${s.value}%`,
                height: "100%",
                background: s.accent ? "var(--color-accent)" : "var(--color-surface-3)",
              }}
            />
            <input
              type="range"
              min={0}
              max={100}
              defaultValue={s.value}
              disabled
              aria-label={`${s.label} (inactive until the model-bearing pack ships)`}
              data-testid={`what-if-input-${s.key}`}
              style={{
                position: "absolute",
                inset: 0,
                width: "100%",
                height: "100%",
                margin: 0,
                opacity: 0,
                cursor: "not-allowed",
              }}
            />
          </div>
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
            —
          </span>
        </div>
      </div>
      <p
        style={{ margin: 0, fontSize: 8.5, lineHeight: 1.4, color: "var(--color-dimmer)" }}
        data-testid="what-if-caption"
      >
        What-if activates with the model-bearing pack — sliders park here until the Honest Model
        ships (ADR-0003).
      </p>
    </div>
  );
}
