import { CardHead } from "./bits";

/**
 * Structure-only until the pack ships the surrender advisor (ADR-0003): the
 * caption keeps the survivorship-bias caveat so the empty number stays honest.
 */
export function SurrenderReadCard() {
  return (
    <section
      className="card3"
      data-testid="surrender-read"
      style={{ padding: 13, flex: 1, minHeight: 0, display: "flex", flexDirection: "column", gap: 8 }}
    >
      <CardHead color="var(--color-info)" label="SURRENDER READ" />
      <div style={{ display: "flex", alignItems: "baseline", gap: 8 }}>
        <span className="mono-n" style={{ font: "700 22px var(--font-mono)", color: "var(--color-dimmer)" }}>
          —
        </span>
        <span style={{ fontSize: 10, color: "var(--color-dimmer)" }}>flip chance at your vote</span>
      </div>
      <div
        style={{
          display: "flex",
          alignItems: "center",
          gap: 9,
          padding: "8px 9px",
          borderRadius: 12,
          background: "var(--color-surface-2)",
        }}
      >
        <span style={{ fontSize: 9.5, color: "var(--color-dim)" }}>At 20 min, before the vote</span>
        <span className="mono-n" style={{ marginLeft: "auto", fontSize: 11, color: "var(--color-dimmer)" }}>
          —
        </span>
      </div>
      <p style={{ margin: "auto 0 0", fontSize: 9.5, lineHeight: 1.5, color: "var(--color-dim)" }}>
        The surrender advisor ships with the next Findings Pack. Calibrated on state, not outcome —
        surrendered games look more winnable in hindsight than they were (survivorship bias).
      </p>
    </section>
  );
}
