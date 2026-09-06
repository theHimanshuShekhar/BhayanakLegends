import type { CSSProperties } from "react";
import type { HabitOutcome, PostGameDigest } from "../../api/types";
import type { FindingsPackV2, PackV2Habit } from "../../api/pack-v2";
import { formatClock, formatRate } from "../format";
import { SectionHead, Unavailable } from "../ui";

const VERDICT_PILL: Record<HabitOutcome["verdict"], CSSProperties> = {
  good: { background: "var(--color-teal-low)", color: "var(--color-teal)" },
  bad: { background: "var(--color-danger-low)", color: "var(--color-soft-rose)" },
  neutral: { background: "var(--color-surface-3)", color: "var(--color-dim)" },
  "n/a": { background: "var(--color-surface-3)", color: "var(--color-dimmer)" },
};

const PERSONAL_FEATURES = [
  { key: "unseen_recall_share_by_15m", label: "Safe recall share by 15m", unit: "share" },
  { key: "avg_banked_gold_at_recall_by_15m", label: "Banked gold at recall by 15m", unit: "gold" },
  { key: "early_fight_participation_rate", label: "Early-fight participation", unit: "share" },
  { key: "first_dragon_by_20m_s", label: "First team-dragon timing", unit: "seconds" },
  { key: "plates_taken_by_14m", label: "Plates taken by 14 minutes", unit: "plate_count" },
] as const;

type PersonalFeatureRow = {
  key: string;
  label: string;
  value: string | null;
  missingReason: string;
  feature: string;
};

function featureValues(value: unknown): Record<string, number | null> | null {
  if (value == null || typeof value !== "object" || Array.isArray(value)) return null;
  return value as Record<string, number | null>;
}

function formatFeatureValue(key: string, value: number): string {
  if (key === "unseen_recall_share_by_15m" || key === "early_fight_participation_rate") {
    return formatRate(value);
  }
  if (key === "first_dragon_by_20m_s") return formatClock(value);
  if (key === "avg_banked_gold_at_recall_by_15m") {
    return `${Math.round(value).toLocaleString("en-US")}g`;
  }
  return `${Math.round(value)} plates`;
}

function personalFeatureRows(digest: PostGameDigest | null): PersonalFeatureRow[] {
  if (digest?.feature_contract_version !== "loltrends-parity-v2") return [];
  const features = featureValues(digest.features);
  if (!features) return [];
  return PERSONAL_FEATURES.map((definition) => {
    const featureValue = features[definition.key] ?? null;
    return {
      key: definition.key,
      label: definition.label,
      value: typeof featureValue === "number" && Number.isFinite(featureValue) ? formatFeatureValue(definition.key, featureValue) : null,
      missingReason: `${definition.label.toLowerCase()} not observed in the required window`,
      feature: definition.key,
    };
  });
}

function populationHabit(pack: FindingsPackV2 | undefined, feature: string): PackV2Habit | null {
  return pack?.habits.find((habit) => habit.feature === feature) ?? null;
}


/** Personal observations stay separate from Findings Pack population effects. */
export function HabitsCard({
  digest,
  pack,
}: {
  digest: PostGameDigest | null;
  pack?: FindingsPackV2;
}) {
  const idle = digest == null;
  const personalRows = personalFeatureRows(digest);
  const outcomeRows = digest?.habits ?? [];
  const unavailable = digest != null && outcomeRows.length === 0 && personalRows.length === 0;
  const win = digest?.win ?? false;
  return (
    <section
      className="card3b"
      aria-labelledby="postgame-habits-heading"
      style={{
        padding: 14,
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
      <SectionHead color={win && !idle ? "var(--color-teal)" : "var(--color-info)"} label={<span id="postgame-habits-heading">Game habits</span>} />
      <div style={{ display: "flex", alignItems: "center", gap: 9 }}>
        <SectionHead level={3} dot={false} label="Personal History observations" />
        <span className="mono-n" style={{ marginLeft: "auto", fontSize: 10, color: "var(--color-dimmer)" }}>
          local v2 features
        </span>
      </div>
      {idle ? (
        <div style={{ display: "flex", alignItems: "center", justifyContent: "center", padding: "16px 8px", borderRadius: 12, border: "1px dashed var(--color-line)", color: "var(--color-dim)", fontSize: 10.5 }}>
          Waiting for the first analyzed game.
        </div>
      ) : unavailable ? (
        <div
          data-testid="habit-unavailable"
          style={{ display: "flex", alignItems: "center", justifyContent: "center", padding: "16px 8px", borderRadius: 12, border: "1px dashed var(--color-line)", color: "var(--color-dim)", fontSize: 10.5, textAlign: "center" }}
        >
          <Unavailable reason="no compatible v2 habit observations reported for this game" />
        </div>
      ) : outcomeRows.length > 0 ? (
        <ul aria-label="Personal habit outcomes" data-testid="habit-outcomes" style={{ display: "flex", flexDirection: "column", gap: 6, listStyle: "none", margin: 0, padding: 0 }}>
          {outcomeRows.map((habit) => {
            const population = populationHabit(pack, habit.key);
            return (
              <li key={habit.key} data-testid={`habit-${habit.key}`} style={{ display: "flex", alignItems: "center", gap: 9, padding: "7px 9px", borderRadius: 12, background: "var(--color-surface-2)", boxShadow: "var(--shadow-z1)" }}>
                <span className="mono-n" style={{ width: 70, fontSize: 9.5, color: "var(--color-dimmer)" }}>{habit.value}</span>
                <span style={{ flex: 1, fontSize: 10.5 }}>{habit.label}</span>
                <span className="pill" style={{ ...VERDICT_PILL[habit.verdict], fontSize: 8, padding: "2px 7px" }}>{habit.verdict}</span>
                {population && (
                  <span style={{ fontSize: 8, color: "var(--color-info)" }}>
                    ×{population.effect.toFixed(2)} {population.unit}
                  </span>
                )}
              </li>
            );
          })}
        </ul>
      ) : (
        <ul aria-label="Personal feature observations" data-testid="habit-feature-observations" style={{ display: "flex", flexDirection: "column", gap: 6, listStyle: "none", margin: 0, padding: 0 }}>
          {personalRows.map((row) => {
            const population = populationHabit(pack, row.feature);
            return (
              <li key={row.key} data-testid={`habit-${row.key}`} style={{ display: "flex", flexDirection: "column", gap: 5, padding: "7px 9px", borderRadius: 12, background: "var(--color-surface-2)", boxShadow: "var(--shadow-z1)" }}>
                <div style={{ display: "flex", alignItems: "baseline", gap: 9 }}>
                  <span style={{ flex: 1, fontSize: 10.5 }}>{row.label}</span>
                  <span className="mono-n" style={{ fontSize: 10, color: "var(--color-teal)" }}>
                    {row.value ?? <Unavailable reason={row.missingReason} />}
                  </span>
                </div>
                <div style={{ fontSize: 8.5, lineHeight: 1.4, color: "var(--color-dimmer)" }}>
                  {population
                    ? `${population.key === "plates_by_14" ? "Diagnostic · era-sensitive" : "Population association"} · ×${population.effect.toFixed(2)} ${population.unit} · ${population.caveats[0]}`
                    : "Population context unavailable for this feature."}
                </div>
              </li>
            );
          })}
        </ul>
      )}
      <SectionHead level={3} dot={false} label="Digest headline" />
      <div style={{ marginTop: "auto", display: "flex", gap: 9, padding: 10, borderRadius: 14, background: "var(--color-accent-low)", boxShadow: "var(--shadow-z1)" }}>
        <p data-testid="digest-headline" style={{ margin: 0, fontSize: 11, lineHeight: 1.55, color: "var(--color-chip-text)" }}>
          {digest ? digest.headline : "Unavailable: no analyzed game yet"}
        </p>
      </div>
    </section>
  );
}
