import type { HabitDef } from "../../api/types";
import { RailHeader } from "../champions/bits";

export function LeverAdoption({ habits }: { habits: HabitDef[] }) {
  return (
    <div
      className="card3b"
      data-testid="lever-adoption"
      style={{ padding: 14, display: "flex", flexDirection: "column", gap: 8 }}
    >
      <RailHeader
        label="LEVER ADOPTION"
        right={
          <span className="pill" style={{ background: "var(--color-info-low)", color: "#cfe3f9" }}>
            Findings Pack
          </span>
        }
      />
      {habits.map((h) => (
        <div
          key={h.key}
          data-testid={`habit-row-${h.key}`}
          style={{
            display: "flex",
            flexDirection: "column",
            gap: 6,
            padding: "8px 10px",
            borderRadius: 13,
            background: "var(--color-surface-3)",
          }}
        >
          <div style={{ display: "flex", alignItems: "center", gap: 9 }}>
            <div style={{ flex: 1 }}>
              <div style={{ font: "600 11px var(--font-mono)" }}>{h.label}</div>
              <div style={{ fontSize: 9, color: "var(--color-dim)" }}>
                +{h.effect_per_sd.toFixed(2)}% WR per SD
              </div>
            </div>
            <span className="mono-n" style={{ fontSize: 10, color: "var(--color-dim)" }}>
              — pending
            </span>
          </div>
          <div
            data-testid={`habit-bar-${h.key}`}
            style={{
              height: 4,
              borderRadius: 999,
              background: "var(--color-deep)",
              overflow: "hidden",
            }}
          >
            <div style={{ width: 0, height: "100%", background: "var(--color-surface-3)" }} />
          </div>
        </div>
      ))}
      <p style={{ margin: 0, fontSize: 8.5, lineHeight: 1.4, color: "var(--color-dimmer)" }}>
        These four survive full statistical controls. Personal trend bars stay neutral until
        timeline features land with the loltrends wheel.
      </p>
    </div>
  );
}
