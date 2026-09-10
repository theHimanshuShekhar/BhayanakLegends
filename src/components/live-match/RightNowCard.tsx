import type { FindingsPackV2 } from "../../api/pack-v2";
import { formatEffectPerSd } from "../format";
import {
  habitEvidence,
  habitEvidenceReleased,
  habitFavorableDirection,
} from "../populationEvidence";
import { SectionHead } from "../ui";

/** Actionable Findings Pack habits are population associations, not live state. */
export function RightNowCard({ pack }: { pack: FindingsPackV2 | undefined }) {
  const habits = habitEvidence(pack).map((habit) => {
    const available = habitEvidenceReleased(habit);
    return {
      ...habit,
      available,
      effectLabel: formatEffectPerSd(
        available ? habit.effect : undefined,
        habit.releaseReason ?? habit.contractIssue ?? "habit evidence unavailable",
      ),
    };
  });
  return (
    <section
      className="card3"
      data-testid="habit-nudges"
      aria-labelledby="right-now-heading"
      style={{ padding: 12, flex: 1, minHeight: 0, display: "flex", flexDirection: "column", gap: 7 }}
    >
      <SectionHead color="var(--color-info)" label={<span id="right-now-heading">RIGHT NOW</span>} />
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
        <span className="pill" style={{ alignSelf: "flex-start", background: "var(--color-accent)", color: "var(--color-bg)" }}>
          Act
        </span>
        <p style={{ margin: 0, fontSize: 10.5, lineHeight: 1.5, color: "var(--color-soft-lavender)" }}>
          Act-level nudges read the live game state — they require the :2999 bridge.
        </p>
      </div>
      <ul aria-label="Population guidance" style={{ display: "flex", flexDirection: "column", gap: 7, listStyle: "none", margin: 0, padding: 0 }}>
        {habits.map((habit) => (
          <li
            key={habit.key}
            data-testid={`habit-nudge-${habit.key}`}
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
              style={{ alignSelf: "flex-start", background: "var(--color-info-low)", color: "var(--color-soft-blue)" }}
            >
              Habit
            </span>
            <p style={{ margin: 0, fontSize: 10.5, lineHeight: 1.5, color: "var(--color-soft-text)" }}>
              {habit.available
                ? `${habitFavorableDirection(habit)} — ${habit.effectLabel}. Observational population association, not a guarantee.`
                : `${habit.label} — Population association unavailable: ${habit.releaseReason ?? habit.contractIssue ?? "evidence is unavailable"}`}
            </p>
          </li>
        ))}
        {habits.length === 0 && (
          <li role="status" style={{ padding: "8px 9px", color: "var(--color-dimmer)", fontSize: 10 }}>
            Unavailable: no valid Findings Pack habit rows are active.
          </li>
        )}
      </ul>
    </section>
  );
}
