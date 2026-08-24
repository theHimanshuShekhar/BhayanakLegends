import type { PackFinding } from "../../api/types";
import { KickerRow } from "./bits";

function pctLabel(v: number): string {
  return v <= 1 ? `${Math.round(v * 100)}%` : `${v}%`;
}

export function CompCard({ findings }: { findings: PackFinding[] }) {
  const n = findings.length;
  return (
    <div
      className="card3"
      data-testid="comp-card"
      style={{ padding: 13, display: "flex", flexDirection: "column", gap: 9 }}
    >
      <KickerRow label="WHEN THE ENEMY TEAM HAS…" />
      <div style={{ display: "grid", gridTemplateColumns: `repeat(${n},1fr)`, gap: 9 }}>
        {findings.map((f, i) => {
          const first = i === 0 && n > 1;
          const last = i === n - 1 && n > 2;
          const background = first
            ? "linear-gradient(150deg,#2b4a44,var(--color-surface-2) 78%)"
            : last
              ? "linear-gradient(150deg,#4d2436,var(--color-surface-2) 78%)"
              : "var(--color-surface-2)";
          const color = first
            ? "var(--color-teal)"
            : last
              ? "var(--color-danger)"
              : undefined;
          return (
            <div
              key={f.key}
              style={{
                padding: 11,
                borderRadius: 14,
                background,
                boxShadow: "var(--shadow-z1)",
                textAlign: "center",
              }}
            >
              <div
                className="mono-n"
                style={{ font: "700 21px var(--font-mono)", color }}
              >
                {f.value != null ? pctLabel(f.value) : "—"}
              </div>
              <div style={{ fontSize: 9, color: "var(--color-dimmer)", marginTop: 3 }}>
                {f.title}
              </div>
            </div>
          );
        })}
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
  const label = v == null ? "—" : v <= 1 ? v.toFixed(2) : String(v);
  return (
    <div
      className="card3b"
      data-testid="damage-fit-card"
      style={{ padding: 13, display: "flex", flexDirection: "column", gap: 9 }}
    >
      <KickerRow
        label="DAMAGE-FIT SCORE"
        right={
          <span
            className="mono-n"
            style={{ font: "700 16px var(--font-mono)", color: "var(--color-teal)" }}
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
            background: "linear-gradient(90deg,#2f7f6d,var(--color-teal))",
          }}
        />
      </div>
      <p style={{ margin: 0, fontSize: 10, lineHeight: 1.5, color: "#cfd3e5" }}>
        {finding.statement}
      </p>
    </div>
  );
}

export function GoldWasteCard({ finding }: { finding: PackFinding }) {
  const v = finding.value ?? 0;
  const width = Math.min(100, Math.round((v / 550) * 100));
  const label = `${v}${finding.unit ?? ""}`;
  return (
    <div
      className="card3"
      data-testid="gold-waste-card"
      style={{ padding: 13, display: "flex", flexDirection: "column", gap: 8 }}
    >
      <KickerRow label="GOLD WASTE" dot="#7a8098" />
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
