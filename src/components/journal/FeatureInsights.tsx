import type {
  HistoryFeatureInsight,
  HistoryFeatureKey,
  HistoryFeatureStatus,
  HistoryFeatureTrajectoryPoint,
} from "../../api/types";
import { formatClock, formatRate } from "../format";
import { Unavailable } from "../ui";

const FEATURE_ORDER: readonly HistoryFeatureKey[] = [
  "unseen_recall_share_by_15m",
  "avg_banked_gold_at_recall_by_15m",
  "early_fight_participation_rate",
  "first_dragon_by_20m_s",
  "plates_taken_by_14m",
];

const FEATURE_LABELS: Record<HistoryFeatureKey, string> = {
  cs10: "Minions at 10 minutes",
  level10: "Level at 10 minutes",
  gold_diff_10: "Gold difference at 10 minutes",
  team_gold_diff_15m: "Team gold difference at 15 minutes",
  recalls_before_15m: "Recalls before 15 minutes",
  avg_banked_gold_at_recall_by_15m: "Banked gold at recall by 15 minutes",
  avg_banked_gold_at_recall_by_20m: "Banked gold at recall by 20 minutes",
  unseen_recall_share_by_15m: "Safe/unseen recall share by 15 minutes",
  unseen_recall_share_by_20m: "Safe/unseen recall share by 20 minutes",
  first_dragon_by_20m_s: "First local-team dragon timing",
  first_riftherald_by_20m_s: "First local-team Herald timing",
  first_baron_by_20m_s: "First local-team Baron timing",
  smite_contests_before_15m: "Smite contests before 15 minutes",
  smite_contests_before_20m: "Smite contests before 20 minutes",
  early_fight_participation_rate: "Early-fight participation",
  plates_taken_by_14m: "Turret plates taken by 14 minutes",
};

function labelFor(key: string): string {
  return FEATURE_LABELS[key as HistoryFeatureKey] ?? key.replace(/_/g, " ");
}

function featureRank(key: string): number {
  const rank = FEATURE_ORDER.indexOf(key as HistoryFeatureKey);
  return rank === -1 ? FEATURE_ORDER.length : rank;
}

function unitFor(key: string): "share" | "gold" | "seconds" | "plates" | "count" {
  if (key.includes("share") || key.includes("participation_rate")) return "share";
  if (key.includes("gold")) return "gold";
  if (key.endsWith("_s")) return "seconds";
  if (key.includes("plates")) return "plates";
  return "count";
}

function formatValue(key: string, value: number): string {
  switch (unitFor(key)) {
    case "share":
      return formatRate(value);
    case "gold":
      return `${Math.round(value).toLocaleString("en-US")}g`;
    case "seconds":
      return formatClock(value);
    case "plates":
      return `${Math.round(value)} plates`;
    default:
      return Math.round(value).toLocaleString("en-US");
  }
}

function formatDelta(key: string, value: number): string {
  const formatted = formatValue(key, Math.abs(value));
  return `${value < 0 ? "−" : "+"}${formatted}`;
}

function statusCopy(status: HistoryFeatureStatus): string {
  if (status === "insufficient-sample") return "Insufficient matching-role sample";
  if (status === "unavailable") return "Observation unavailable";
  return "Available observation";
}

function statusColor(status: HistoryFeatureStatus): string {
  if (status === "available") return "var(--color-teal)";
  if (status === "insufficient-sample") return "var(--color-amber)";
  return "var(--color-dimmer)";
}

function FeatureInsightRow({ row }: { row: HistoryFeatureInsight }) {
  const label = labelFor(row.feature_key);
  const current = row.current_value != null
    ? formatValue(row.feature_key, row.current_value)
    : null;
  const roleReference = row.status === "available" && row.role_baseline != null
    ? formatValue(row.feature_key, row.role_baseline)
    : null;
  const delta = row.status === "available" && row.delta != null
    ? formatDelta(row.feature_key, row.delta)
    : null;
  return (
    <li
      data-testid={`feature-insight-${row.feature_key}`}
      style={{
        display: "flex",
        flexDirection: "column",
        gap: 6,
        padding: "9px 10px",
        borderRadius: 12,
        background: "var(--color-surface-2)",
        boxShadow: "var(--shadow-z1)",
      }}
    >
      <div style={{ display: "flex", flexWrap: "wrap", alignItems: "baseline", gap: 8 }}>
        <strong style={{ flex: "1 1 190px", minWidth: 0, fontSize: 10.5, fontWeight: 500 }}>{label}</strong>
        <span className="mono-n" style={{ color: statusColor(row.status), fontSize: 10.5 }}>
          {current ?? <Unavailable reason={row.caveat || statusCopy(row.status)} />}
        </span>
      </div>
      <div style={{ display: "flex", flexWrap: "wrap", gap: 8, fontSize: 8.5, color: "var(--color-dim)" }}>
        <span>{statusCopy(row.status)}</span>
        <span>·</span>
        <span>{row.sample_size.toLocaleString("en-US")} observations</span>
        {roleReference != null && (
          <>
            <span>·</span>
            <span>matching-role reference {roleReference}</span>
          </>
        )}
        {delta != null && (
          <>
            <span>·</span>
            <span>difference {delta}</span>
          </>
        )}
      </div>
      <p style={{ margin: 0, fontSize: 8.5, lineHeight: 1.45, color: "var(--color-dimmer)" }}>
        {row.caveat || "Descriptive Personal History observation; not a causal recommendation."}
      </p>
    </li>
  );
}

function FeatureTrajectory({
  featureKey,
  points,
}: {
  featureKey: string;
  points: HistoryFeatureTrajectoryPoint[];
}) {
  const available = points.filter((point) => point.status === "available" && point.value != null);
  const latest = available.slice(-8);
  const first = points[0];
  return (
    <li
      data-testid={`feature-trajectory-${featureKey}`}
      style={{
        display: "flex",
        flexDirection: "column",
        gap: 6,
        padding: "9px 10px",
        borderRadius: 12,
        background: "var(--color-surface-2)",
        boxShadow: "var(--shadow-z1)",
      }}
    >
      <div style={{ display: "flex", alignItems: "baseline", justifyContent: "space-between", gap: 8 }}>
        <strong style={{ fontSize: 10.5, fontWeight: 500 }}>{labelFor(featureKey)}</strong>
        <span className="mono-n" style={{ fontSize: 9, color: "var(--color-dim)" }}>
          {available.length} observed points
        </span>
      </div>
      {latest.length > 0 ? (
        <ol
          aria-label={`${labelFor(featureKey)} trajectory points`}
          style={{ display: "flex", flexWrap: "wrap", gap: 6, listStyle: "none", padding: 0, margin: 0 }}
        >
          {latest.map((point, index) => (
            <li
              key={`${point.played_at}-${index}`}
              style={{ minWidth: 82, padding: "5px 6px", border: "1px solid var(--color-line)", borderRadius: 8 }}
            >
              <div className="mono-n" style={{ fontSize: 9, color: "var(--color-teal)" }}>
                {point.value == null ? "—" : formatValue(featureKey, point.value)}
              </div>
              <div style={{ marginTop: 2, fontSize: 7.5, color: "var(--color-dimmer)" }}>
                {point.played_at.slice(0, 10) || "undated"}
              </div>
            </li>
          ))}
        </ol>
      ) : (
        <Unavailable reason={first?.caveat || "No compatible observations in this trajectory"} />
      )}
      <p style={{ margin: 0, fontSize: 8.5, lineHeight: 1.45, color: "var(--color-dimmer)" }}>
        {first?.caveat || "Descriptive local trajectory; inspect the matches rather than treating movement as proof of cause."}
      </p>
    </li>
  );
}

export function FeatureInsights({
  insights,
  trajectories,
}: {
  insights: HistoryFeatureInsight[];
  trajectories: HistoryFeatureTrajectoryPoint[];
}) {
  const orderedInsights = [...insights].sort(
    (left, right) => featureRank(left.feature_key) - featureRank(right.feature_key),
  );
  const keys = [...new Set(trajectories.map((point) => point.feature_key))].sort(
    (left, right) => featureRank(left) - featureRank(right),
  );
  return (
    <section
      aria-labelledby="journal-feature-insights-heading"
      data-testid="journal-feature-insights"
      style={{ display: "flex", flexDirection: "column", gap: 9 }}
    >
      <div style={{ display: "flex", alignItems: "baseline", justifyContent: "space-between", gap: 8 }}>
        <h3 id="journal-feature-insights-heading" className="route-subheading">Contracted feature observations</h3>
        <span className="mono-n" style={{ fontSize: 8.5, color: "var(--color-teal)" }}>ROLE-ADJUSTED · LOCAL</span>
      </div>
      {orderedInsights.length > 0 ? (
        <ul aria-label="Role-adjusted Personal History feature observations" style={{ display: "flex", flexDirection: "column", gap: 6, listStyle: "none", padding: 0, margin: 0 }}>
          {orderedInsights.map((row) => <FeatureInsightRow key={row.feature_key} row={row} />)}
        </ul>
      ) : (
        <Unavailable reason="No contracted Personal History observations are available for this filter" />
      )}
      <div>
        <h3 className="route-subheading" style={{ marginBottom: 7 }}>Feature trajectories</h3>
        {keys.length > 0 ? (
          <ul aria-label="Personal History feature trajectories" style={{ display: "flex", flexDirection: "column", gap: 6, listStyle: "none", padding: 0, margin: 0 }}>
            {keys.map((key) => (
              <FeatureTrajectory
                key={key}
                featureKey={key}
                points={trajectories.filter((point) => point.feature_key === key)}
              />
            ))}
          </ul>
        ) : (
          <Unavailable reason="No trajectory points meet the contracted observation rules" />
        )}
      </div>
      <p style={{ margin: 0, fontSize: 9, lineHeight: 1.45, color: "var(--color-dim)" }}>
        Matching-role references adjust for role mix. These are descriptive associations from Personal History, not coaching instructions or causal guarantees.
      </p>
    </section>
  );
}
