import type { FindingsPack } from "../../api/types";
import { formatPercentagePoints, formatRate } from "../format";
import { SectionHead } from "../ui";

export function ObjectivesCard({ pack }: { pack: FindingsPack | undefined }) {
  const o = pack?.objectives;
  return (
    <section
      className="card3"
      data-testid="objectives-computed"
      aria-labelledby="objectives-computed-heading"
      style={{ padding: 12, display: "flex", flexDirection: "column", gap: 8 }}
    >
      <SectionHead color="var(--color-info)" label={<span id="objectives-computed-heading">OBJECTIVES · COMPUTED</span>} />
      <div
        data-testid="objective-dragon"
        style={{
          display: "flex",
          alignItems: "center",
          gap: 9,
          padding: "9px 10px",
          borderRadius: 13,
          background: "linear-gradient(140deg,#2b4a44,var(--color-surface-2) 78%)",
          boxShadow: "0 3px 0 rgba(0,0,0,.5),0 0 0 1.5px rgba(87,207,180,.5)",
        }}
      >
        <div
          style={{
            width: 26,
            height: 26,
            flex: "none",
            borderRadius: 8,
            background: "linear-gradient(150deg,var(--color-teal),#1f6b5c)",
          }}
        />
        <div style={{ flex: 1 }}>
          <div style={{ font: "600 11px var(--font-mono)", color: "#bdeee1" }}>Drake</div>
          <span
            className="pill"
            style={{ background: "rgba(0,0,0,.2)", color: "#bdeee1", fontSize: 8, padding: "2px 6px" }}
          >
            checkpoint, not weapon
          </span>
        </div>
        <div style={{ textAlign: "right" }}>
          <div className="mono-n" style={{ font: "700 15px var(--font-mono)", color: "var(--color-soft-blue)" }}>
            {formatRate(o?.dragon_denial_win_rate, "Findings Pack objective rate unavailable")}
          </div>
          <div style={{ fontSize: 7.5, letterSpacing: ".06em", color: "var(--color-dimmer)" }}>DENIAL WR</div>
        </div>
      </div>
      <div
        data-testid="objective-baron"
        style={{
          display: "flex",
          alignItems: "center",
          gap: 9,
          padding: "8px 10px",
          borderRadius: 13,
          background: "var(--color-surface-2)",
          boxShadow: "var(--shadow-z1)",
        }}
      >
        <div
          style={{
            width: 26,
            height: 26,
            flex: "none",
            borderRadius: 8,
            background: "linear-gradient(150deg,#4a5570,#232a3d)",
          }}
        />
        <div style={{ flex: 1 }}>
          <div style={{ font: "600 11px var(--font-mono)" }}>Baron</div>
          <span
            className="pill"
            style={{ background: "var(--color-teal-low)", color: "var(--color-teal)", fontSize: 8, padding: "2px 6px" }}
          >
            comeback tool
          </span>
        </div>
        <div style={{ textAlign: "right" }}>
          <div className="mono-n" style={{ font: "700 14px var(--font-mono)", color: "var(--color-soft-blue)" }}>
            {formatRate(o?.baron_pre25_win_rate, "Findings Pack objective rate unavailable")}
          </div>
          <div style={{ fontSize: 7.5, letterSpacing: ".06em", color: "var(--color-dimmer)" }}>PRE-25 WR</div>
        </div>
      </div>
      <p
        data-testid="objectives-caption"
        style={{ margin: 0, fontSize: 9, lineHeight: 1.45, color: "var(--color-dimmer)" }}
      >
        First dragon before 20 wins {formatRate(o?.first_dragon_pre20_win_rate, "Findings Pack objective rate unavailable")} of games; Baron from behind
        lifts win rate {formatPercentagePoints(o?.baron_comeback_lift_pp, "Findings Pack comeback lift unavailable")}.
      </p>
    </section>
  );
}
