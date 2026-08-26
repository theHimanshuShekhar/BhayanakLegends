import type { FindingsPack } from "../../api/types";
import { pct } from "../ui";
import { Dot } from "./bits";

/**
 * RIGHT NOW nudges. Habits are the pack's actionable tier (ADR-0003: they may
 * instruct); the trap line describes population trap picks; act-level nudges
 * need live game state and stay an idle caption until the bridge connects.
 */
export function RightNowCard({ pack }: { pack: FindingsPack | undefined }) {
  const habits = pack?.habits ?? [];
  const traps = (pack?.trap_picks ?? []).slice(0, 3);
  return (
    <section
      className="card3"
      data-testid="habit-nudges"
      style={{ padding: 12, flex: 1, minHeight: 0, display: "flex", flexDirection: "column", gap: 7 }}
    >
      <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
        <Dot color="#7a8098" />
        <h2 style={{ margin: 0, font: "700 9.5px var(--font-mono)", letterSpacing: ".11em", color: "var(--color-dim)" }}>
          RIGHT NOW
        </h2>
        <div aria-hidden="true" style={{ flex: 1, height: 1, background: "linear-gradient(90deg,var(--color-line),transparent)" }} />
      </div>
      <div
        style={{
          display: "flex",
          gap: 9,
          padding: "9px 10px",
          borderRadius: 13,
          background: "linear-gradient(150deg,#3a3468,var(--color-surface-2) 75%)",
          boxShadow: "0 3px 0 rgba(0,0,0,.5),0 0 0 1.5px rgba(145,132,217,.5)",
        }}
      >
        <span className="pill" style={{ alignSelf: "flex-start", background: "var(--color-accent)", color: "#0e1020" }}>
          Act
        </span>
        <p style={{ margin: 0, fontSize: 10.5, lineHeight: 1.5, color: "#e0ddf5" }}>
          Act-level nudges read the live game state — they land with the :2999 bridge.
        </p>
      </div>
      <ul aria-label="Live guidance" style={{ display: "flex", flexDirection: "column", gap: 7, listStyle: "none", margin: 0, padding: 0 }}>
        {habits.map((h) => (
          <li
            key={h.key}
            data-testid={`habit-nudge-${h.key}`}
            style={{
              display: "flex",
              gap: 9,
              padding: "8px 9px",
              borderRadius: 13,
              background: "var(--color-surface-2)",
              boxShadow: "var(--shadow-z1)",
            }}
          >
            <span
              className="pill"
              style={{ alignSelf: "flex-start", background: "var(--color-info-low)", color: "#cfe3f9" }}
            >
              Habit
            </span>
            <p style={{ margin: 0, fontSize: 10.5, lineHeight: 1.5, color: "#cfd3e5" }}>
              {h.label} — worth ×{h.effect_per_sd.toFixed(2)} per SD.
            </p>
          </li>
        ))}
        {traps.length > 0 && (
          <li
            data-testid="trap-nudge"
            style={{
              display: "flex",
              gap: 9,
              padding: "8px 9px",
              borderRadius: 13,
              background: "var(--color-surface-2)",
              boxShadow: "var(--shadow-z1)",
            }}
          >
            <span
              className="pill"
              style={{ alignSelf: "flex-start", background: "var(--color-amber-low)", color: "var(--color-amber)" }}
            >
              Trap
            </span>
            <p style={{ margin: 0, fontSize: 10.5, lineHeight: 1.5, color: "#cfd3e5" }}>
              Trap picks this patch — {traps.map((t) => `${t.champion} ${pct(t.win_rate)}`).join(" · ")}.
            </p>
          </li>
        )}
      </ul>
    </section>
  );
}
