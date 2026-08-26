import type { FindingsPack } from "../../api/types";
import { pct } from "../ui";
import { PanelHeading, Subheading, pp, UnavailableValue } from "./bits";
/** Objective read cards: digest headline context + pack.objectives takeaways. */
export function ObjectiveReadCard({ pack }: { pack: FindingsPack | undefined }) {
  const o = pack?.objectives;
  return (
    <section
      className="card3"
      data-testid="objective-read"
      aria-labelledby="postgame-objectives-heading"
      style={{ padding: 13, display: "flex", flexDirection: "column", gap: 8 }}
    >
      <PanelHeading color="var(--color-info)">
        <span id="postgame-objectives-heading">Objectives</span>
      </PanelHeading>
      <Subheading>Objective reads</Subheading>
      <ul
        aria-label="Objective reads"
        style={{ display: "flex", flexDirection: "column", gap: 8, listStyle: "none", margin: 0, padding: 0 }}
      >
        <li
          style={{
            display: "flex",
            alignItems: "center",
            gap: 9,
            padding: "8px 9px",
            borderRadius: 12,
            background: "var(--color-surface-2)",
            boxShadow: "var(--shadow-z1)",
          }}
        >
          <div style={{ flex: 1 }}>
            <div style={{ font: "600 11px var(--font-mono)" }}>Dragons</div>
            <div style={{ fontSize: 9, color: "var(--color-dimmer)" }}>checkpoint, not weapon</div>
          </div>
          <span
            className="pill"
            data-testid="read-dragons"
            style={{
              background: "var(--color-teal-low)",
              color: "var(--color-teal)",
              fontSize: 8,
              padding: "2px 7px",
            }}
          >
            {o?.dragon_denial_win_rate == null ? <UnavailableValue /> : `denial ${pct(o.dragon_denial_win_rate)}`}
          </span>
        </li>
        <li
          style={{
            display: "flex",
            alignItems: "center",
            gap: 9,
            padding: "8px 9px",
            borderRadius: 12,
            background: "var(--color-surface-2)",
            boxShadow: "var(--shadow-z1)",
          }}
        >
          <div style={{ flex: 1 }}>
            <div style={{ font: "600 11px var(--font-mono)" }}>Baron</div>
            <div style={{ fontSize: 9, color: "var(--color-dimmer)" }}>
              comeback tool · pre-25 {o?.baron_pre25_win_rate == null ? <UnavailableValue /> : pct(o.baron_pre25_win_rate)}
            </div>
          </div>
          <span
            className="pill"
            data-testid="read-baron"
            style={{
              background: "var(--color-amber-low)",
              color: "var(--color-amber)",
              fontSize: 8,
              padding: "2px 7px",
            }}
          >
            {o?.baron_comeback_lift_pp == null ? <UnavailableValue /> : `${pp(o.baron_comeback_lift_pp)} lift`}
          </span>
        </li>
      </ul>
      <p style={{ margin: 0, fontSize: 9.5, lineHeight: 1.5, color: "var(--color-dim)" }}>
        First dragon before 20 wins {o?.first_dragon_pre20_win_rate == null ? <UnavailableValue /> : pct(o.first_dragon_pre20_win_rate)} of games — the swing is
        denial, not possession.
      </p>
    </section>
  );
}
