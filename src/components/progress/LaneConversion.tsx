import type { PackFinding } from "../../api/types";

export function LaneConversion({ finding }: { finding: PackFinding }) {
  return (
    <div
      className="card3"
      data-testid="lane-conversion"
      style={{ padding: 14, display: "flex", flexDirection: "column", gap: 8 }}
    >
      <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
        <span
          className="pill"
          style={{ background: "var(--color-amber-low)", color: "var(--color-amber)" }}
        >
          Lane conversion
        </span>
        <span
          style={{
            font: "700 9.5px var(--font-mono)",
            letterSpacing: ".14em",
            color: "var(--color-dim)",
          }}
        >
          LEADS ARE RAW MATERIAL
        </span>
      </div>
      <p style={{ margin: 0, fontSize: 10, lineHeight: 1.5, color: "var(--color-dim)" }}>
        {finding.statement}
      </p>
    </div>
  );
}
