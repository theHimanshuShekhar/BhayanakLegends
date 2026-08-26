import type { PackFinding } from "../../api/types";
import { formatGold, formatRate } from "../format";
import { SectionHead } from "../ui";

function findingRate(value: number | null): string {
  // Findings values arrive either as a fraction (<=1) or an already-scaled
  // percent (>1); normalize both through the shared rate formatter.
  return formatRate(value == null ? null : value > 1 ? value / 100 : value, "finding value unavailable");
}

export function CompCard({ findings }: { findings: PackFinding[] }) {
  const n = findings.length;
  return (
    <div
      className="card3"
      data-testid="comp-card"
      style={{ padding: 13, display: "flex", flexDirection: "column", gap: 9 }}
    >
      <SectionHead label="WHEN THE ENEMY TEAM HAS…" />
      <div style={{ display: "grid", gridTemplateColumns: `repeat(${n},1fr)`, gap: 9 }}>
        {findings.map((f) => (
          <div
            key={f.key}
            style={{
              padding: 11,
              borderRadius: 14,
              background: "var(--color-surface-2)",
              boxShadow: "var(--shadow-z1)",
              textAlign: "center",
            }}
          >
            {/* Findings Pack population value: blue, regardless of framing. */}
            <div
              className="mono-n"
              style={{ font: "700 21px var(--font-mono)", color: "var(--color-info)" }}
            >
              {findingRate(f.value)}
            </div>
            <div style={{ fontSize: 9, color: "var(--color-dimmer)", marginTop: 3 }}>
              {f.title}
            </div>
          </div>
        ))}
      </div>
      <p style={{ margin: 0, fontSize: 10, lineHeight: 1.5, color: "var(--color-dim)" }}>
        Directionally useful, not gospel — comp damage-share splits are approximate.
      </p>
    </div>
  );
}

export function DamageFitCard({ finding }: { finding: PackFinding }) {
  const v = finding.value;
  const norm = v == null ? 0 : v <= 1 ? v : Math.min(v, 100) / 100;
  const label = v == null ? "Unavailable: damage-fit score is missing" : v <= 1 ? v.toFixed(2) : String(v);
  return (
    <div
      className="card3b"
      data-testid="damage-fit-card"
      style={{ padding: 13, display: "flex", flexDirection: "column", gap: 9 }}
    >
      <SectionHead
        label="DAMAGE-FIT SCORE"
        color="var(--color-info)"
        right={
          <span
            className="mono-n"
            style={{ font: "700 16px var(--font-mono)", color: "var(--color-info)" }}
          >
            {label}
          </span>
        }
      />
      <div
        style={{
          height: 9,
          borderRadius: 999,
          background: "var(--color-deep)",
          boxShadow: "inset 0 2px 5px rgba(0,0,0,.8)",
          overflow: "hidden",
        }}
      >
        <div
          style={{
            width: `${Math.round(norm * 100)}%`,
            height: "100%",
            borderRadius: 999,
            background: "linear-gradient(90deg,var(--color-info-low),var(--color-info))",
          }}
        />
      </div>
      <p style={{ margin: 0, fontSize: 10, lineHeight: 1.5, color: "var(--color-soft-text)" }}>
        {finding.statement}
      </p>
    </div>
  );
}

export function GoldWasteCard({ finding }: { finding: PackFinding }) {
  const value = finding.value;
  const width = value == null ? 0 : Math.min(100, Math.round((value / 550) * 100));
  const label = value == null ? "Unavailable: gold waste value is missing" : formatGold(value);
  return (
    <div
      className="card3"
      data-testid="gold-waste-card"
      style={{ padding: 13, display: "flex", flexDirection: "column", gap: 8 }}
    >
      <SectionHead label="GOLD WASTE" color="var(--color-amber)" />
      <div style={{ display: "flex", alignItems: "baseline", gap: 7 }}>
        <span
          className="mono-n"
          style={{ font: "700 24px var(--font-mono)", color: "var(--color-amber)" }}
        >
          {label}
        </span>
        <span style={{ fontSize: 9.5, color: "var(--color-dimmer)" }}>
          avg wasted per completed item
        </span>
      </div>
      <div
        style={{
          height: 7,
          borderRadius: 999,
          background: "var(--color-deep)",
          overflow: "hidden",
        }}
      >
        <div
          style={{
            width: `${width}%`,
            height: "100%",
            background: "linear-gradient(90deg,#a3811f,var(--color-amber))",
          }}
        />
      </div>
      <p style={{ margin: 0, fontSize: 9.5, lineHeight: 1.5, color: "var(--color-dim)" }}>
        {finding.statement}
      </p>
      <p style={{ margin: "auto 0 0", fontSize: 9, lineHeight: 1.5, color: "var(--color-dimmer)" }}>
        v1 proxy metric — pairs with the spend-before-backing habit nudge.
      </p>
    </div>
  );
}
