import type { CSSProperties } from "react";
import type { HabitOutcome, PostGameDigest } from "../../api/types";

const VERDICT_PILL: Record<HabitOutcome["verdict"], CSSProperties> = {
  good: { background: "var(--color-teal-low)", color: "var(--color-teal)" },
  bad: { background: "var(--color-danger-low)", color: "#f4c3ce" },
  neutral: { background: "var(--color-surface-3)", color: "var(--color-dim)" },
  "n/a": { background: "var(--color-surface-3)", color: "var(--color-dimmer)" },
};

/** Habit rows carry this game's verdicts; the accent box holds the digest headline. */
export function HabitsCard({ digest }: { digest: PostGameDigest | null }) {
  const idle = digest == null;
  const unavailable = digest != null && digest.habits.length === 0;
  const win = digest?.win ?? false;
  return (
    <section
      className="card3b"
      style={{
        padding: 14,
        flex: 1,
        minHeight: 0,
        display: "flex",
        flexDirection: "column",
        gap: 9,
        background: idle
          ? "var(--color-surface-2)"
          : win
            ? "linear-gradient(165deg,#1c2d28,var(--color-surface-2) 65%)"
            : "linear-gradient(165deg,#2d1c28,var(--color-surface-2) 65%)",
      }}
    >
      <div style={{ display: "flex", alignItems: "center", gap: 9 }}>
        <span
          className="pill"
          style={
            idle
              ? { background: "var(--color-surface-3)", color: "var(--color-dim)" }
              : {
                  background: win ? "var(--color-teal-low)" : "var(--color-danger-low)",
                  color: win ? "var(--color-teal)" : "#f4c3ce",
                }
          }
        >
          Habits
        </span>
        <span className="mono-n" style={{ marginLeft: "auto", fontSize: 10, color: "var(--color-dimmer)" }}>
          verdicts from this game
        </span>
      </div>
      {idle ? (
        <div
          style={{
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
            padding: "16px 8px",
            borderRadius: 12,
            border: "1px dashed var(--color-line)",
            color: "var(--color-dim)",
            fontSize: 10.5,
          }}
        >
          habit verdicts land with the first analyzed game
        </div>
      ) : unavailable ? (
        <div
          data-testid="habit-unavailable"
          style={{
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
            padding: "16px 8px",
            borderRadius: 12,
            border: "1px dashed var(--color-line)",
            color: "var(--color-dim)",
            fontSize: 10.5,
            textAlign: "center",
          }}
        >
          No habit outcomes available: this game has no contracted extractor and threshold.
        </div>
      ) : (
        <div style={{ display: "flex", flexDirection: "column", gap: 6 }} data-testid="habit-outcomes">
          {digest.habits.map((h) => (
            <div
              key={h.key}
              data-testid={`habit-${h.key}`}
              style={{
                display: "flex",
                alignItems: "center",
                gap: 9,
                padding: "7px 9px",
                borderRadius: 12,
                background: "var(--color-surface-2)",
                boxShadow: "var(--shadow-z1)",
              }}
            >
              <span className="mono-n" style={{ width: 44, fontSize: 9.5, color: "var(--color-dimmer)" }}>
                {h.value}
              </span>
              <span style={{ flex: 1, fontSize: 10.5 }}>{h.label}</span>
              <span className="pill" style={{ ...VERDICT_PILL[h.verdict], fontSize: 8, padding: "2px 7px" }}>
                {h.verdict}
              </span>
            </div>
          ))}
        </div>
      )}
      <div
        style={{
          marginTop: "auto",
          display: "flex",
          gap: 9,
          padding: 10,
          borderRadius: 14,
          background: "var(--color-accent-low)",
          boxShadow: "var(--shadow-z1)",
        }}
      >
        <p data-testid="digest-headline" style={{ margin: 0, fontSize: 11, lineHeight: 1.55, color: "#e7e5fe" }}>
          {digest ? digest.headline : "The read of your game lands here once a digest exists."}
        </p>
      </div>
    </section>
  );
}
