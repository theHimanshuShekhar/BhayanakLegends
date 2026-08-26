import { SectionHead } from "../ui";

const SLIDERS = [
  { key: "gold_diff_10", label: "Gold diff @10" },
  { key: "plates14", label: "Plates by 14" },
  { key: "safe-recalls", label: "Safe recalls" },
];

const UNAVAILABLE_REASON = "the Honest Model contract is absent";

export function WhatIfPanel() {
  return (
    <div
      className="card3b"
      data-testid="what-if-panel"
      style={{ padding: 13, display: "flex", flexDirection: "column", gap: 8 }}
    >
      <SectionHead level={3} label="WHAT-IF SIMULATOR · UNAVAILABLE" color="var(--color-info)" />
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
            <span className="mono-n" style={{ color: "var(--color-dimmer)" }}>—</span>
          </div>
          <div
            aria-label={`${s.label} unavailable: ${UNAVAILABLE_REASON}`}
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
          <span style={{ fontSize: 9.5, color: "var(--color-chip-text)" }}>Predicted win rate</span>
          <span
            className="mono-n"
            data-testid="what-if-prediction"
            style={{ font: "700 16px var(--font-mono)", color: "var(--color-chip-text)" }}
          >
            Unavailable
          </span>
        </div>
      </div>
      <p
        style={{ margin: 0, fontSize: 8.5, lineHeight: 1.4, color: "var(--color-dimmer)" }}
        data-testid="what-if-caption"
      >
        Personal what-if estimates are unavailable because the Honest Model contract is absent.
      </p>
    </div>
  );
}
