import { useState, type FormEvent } from "react";
import { useHistoryInsights } from "../../api/hooks";
import { FeatureInsights } from "./FeatureInsights";
import { classifyApiError } from "../../api/client";
import type { HistoryInsights, InsightWindow, Role } from "../../api/types";
import { formatRate as pct } from "../format";
import { EmptyState, Unavailable } from "../ui";

type RoleInsight = HistoryInsights["roles"][number];
type ChampionInsight = HistoryInsights["champions"][number];
type ReviewWindow = InsightWindow;
type SampleStatus = RoleInsight["sample_status"];
type InsightFilters = { role?: Role; champion?: string };

const ROLE_OPTIONS: readonly Role[] = ["TOP", "JUNGLE", "MIDDLE", "BOTTOM", "UTILITY", "UNKNOWN"];
function reviewWindows(value: unknown): { latest: ReviewWindow; preceding: ReviewWindow } | null {
  if (value == null || typeof value !== "object" || Array.isArray(value)) return null;
  const windows = value as Record<string, unknown>;
  const latest = windows.latest;
  const preceding = windows.preceding;
  if (!isReviewWindow(latest) || !isReviewWindow(preceding)) return null;
  return { latest, preceding };
}

function isReviewWindow(value: unknown): value is ReviewWindow {
  if (value == null || typeof value !== "object" || Array.isArray(value)) return false;
  const window = value as Record<string, unknown>;
  return (
    (window.name === "latest" || window.name === "preceding") &&
    Number.isInteger(window.games) &&
    Number.isInteger(window.wins) &&
    typeof window.win_rate === "number" &&
    (window.sample_status === "insufficient" || window.sample_status === "review") &&
    (window.completeness === "full" || window.completeness === "partial" || window.completeness === "unavailable")
  );
}

function completenessCopy(window: ReviewWindow): string {
  if (window.completeness === "unavailable") return "No preceding queue yet";
  if (window.completeness === "partial") return `${window.games} of 50 matches`;
  return "50 matches";
}

function ProfileStatus({ status }: { status: SampleStatus }) {
  const isReviewable = status === "review";
  return (
    <span
      style={{
        display: "inline-flex",
        flexDirection: "column",
        gap: 2,
        color: isReviewable ? "var(--color-teal)" : "var(--color-amber)",
      }}
    >
      <span style={{ fontSize: 9, letterSpacing: ".04em", textTransform: "uppercase" }}>
        {isReviewable ? "Reviewable sample" : "Insufficient sample"}
      </span>
      <span style={{ color: "var(--color-dim)", fontSize: 9 }}>
        {isReviewable
          ? "Descriptive local result"
          : "Review prompt only — too few games for a stable read"}
      </span>
    </span>
  );
}

function ProfileTable({
  testId,
  title,
  rows,
}: {
  testId: string;
  title: string;
  rows: Array<RoleInsight | ChampionInsight>;
}) {
  const champions = rows.length > 0 && "champion" in rows[0];
  return (
    <div className="table-scroll" role="region" aria-label={`${title} table`}>
      <table
        className="mono-n w-full text-left"
        style={{ fontSize: 10.5, borderCollapse: "collapse" }}
        data-testid={testId}
      >
        <caption>{title}</caption>
        <thead>
          <tr
            style={{
              fontSize: 9,
              letterSpacing: ".08em",
              textTransform: "uppercase",
              color: "var(--color-dimmer)",
            }}
          >
            <th scope="col" style={{ padding: "4px 8px 4px 0", fontWeight: 400 }}>
              {champions ? "champion" : "role"}
            </th>
            {champions && (
              <th scope="col" style={{ padding: "4px 8px 4px 0", fontWeight: 400 }}>
                roles
              </th>
            )}
            <th scope="col" style={{ padding: "4px 8px 4px 0", fontWeight: 400 }}>
              games
            </th>
            <th scope="col" style={{ padding: "4px 8px 4px 0", fontWeight: 400 }}>
              wins
            </th>
            <th scope="col" style={{ padding: "4px 0", fontWeight: 400 }}>
              win rate
            </th>
            <th scope="col" style={{ padding: "4px 0 4px 14px", fontWeight: 400 }}>
              sample
            </th>
          </tr>
        </thead>
        <tbody>
          {rows.map((row) => (
            <tr
              key={"champion" in row ? row.champion : row.role}
              style={{ borderTop: "1px solid var(--color-line)", verticalAlign: "top" }}
            >
              <th scope="row" style={{ padding: "7px 8px 7px 0", textAlign: "left", fontWeight: 500 }}>
                {"champion" in row ? row.champion : row.role}
              </th>
              {champions && (
                <td style={{ padding: "7px 8px 7px 0", color: "var(--color-dim)" }}>
                  {(row as ChampionInsight).roles.join(", ")}
                </td>
              )}
              <td style={{ padding: "7px 8px 7px 0", color: "var(--color-dim)" }}>{row.games}</td>
              <td style={{ padding: "7px 8px 7px 0", color: "var(--color-dim)" }}>{row.wins}</td>
              <td style={{ padding: "7px 0" }}>{pct(row.win_rate)}</td>
              <td style={{ padding: "7px 0 7px 14px" }}>
                <ProfileStatus status={row.sample_status} />
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function ReviewQueue({ window }: { window: ReviewWindow }) {
  return (
    <div
      style={{
        flex: "1 1 220px",
        minWidth: 0,
        padding: "9px 10px",
        border: "1px solid var(--color-line)",
        borderRadius: "var(--radius-md)",
        background: "var(--color-surface-2)",
      }}
      data-testid={`review-window-${window.name}`}
    >
      <div style={{ display: "flex", alignItems: "baseline", justifyContent: "space-between", gap: 8 }}>
        <strong style={{ font: "var(--type-label)", color: "var(--color-soft-text)" }}>
          {window.name === "latest" ? "Latest 50" : "Preceding 50"}
        </strong>
        <span className="mono-n" style={{ fontSize: 10, color: "var(--color-dim)" }}>
          {completenessCopy(window)}
        </span>
      </div>
      {window.completeness === "unavailable" ? (
        <div style={{ marginTop: 8, fontSize: 10.5 }}>
          <Unavailable reason="Not enough filtered history" />
        </div>
      ) : (
        <div style={{ display: "flex", gap: 16, marginTop: 9, alignItems: "baseline" }}>
          <span className="mono-n" style={{ font: "700 15px var(--font-mono)" }}>
            {window.games} games
          </span>
          <span className="mono-n" style={{ color: "var(--color-teal)" }}>
            {window.wins} wins · {pct(window.win_rate)}
          </span>
        </div>
      )}
      <div style={{ marginTop: 7, fontSize: 9, color: "var(--color-dim)" }}>
        {window.completeness === "partial"
          ? "Partial window — no games were invented to fill it."
          : window.completeness === "full"
            ? "Personal History review queue"
            : "A preceding queue appears after enough filtered games."}
      </div>
    </div>
  );
}

export function InsightsProfiles() {
  const [role, setRole] = useState<"" | Role>("");
  const [championInput, setChampionInput] = useState("");
  const [filters, setFilters] = useState<InsightFilters>({});
  const insights = useHistoryInsights(filters);
  const windows = reviewWindows(insights.data?.windows);

  function submitFilters(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const next: InsightFilters = {};
    if (role) next.role = role;
    const champion = championInput.trim();
    if (champion) next.champion = champion;
    setFilters(next);
  }

  return (
    <section
      className="card3b"
      aria-labelledby="journal-insights-heading"
      aria-busy={insights.isLoading}
      style={{ padding: 14, display: "flex", flexDirection: "column", gap: 11 }}
      data-testid="journal-insights"
    >
      <div style={{ display: "flex", alignItems: "baseline", justifyContent: "space-between", gap: 10 }}>
        <h2 id="journal-insights-heading" className="route-panel-heading">
          Review prompts
        </h2>
        <span className="mono-n" style={{ fontSize: 9, color: "var(--color-teal)" }}>
          PERSONAL HISTORY · LOCAL ONLY
        </span>
      </div>
      <p style={{ margin: 0, fontSize: 10.5, color: "var(--color-dim)" }}>
        Role and champion profiles describe this machine&apos;s persisted matches. They are review prompts,
        not population tiers or matchup verdicts.
      </p>

      <form
        onSubmit={submitFilters}
        style={{ display: "flex", flexWrap: "wrap", gap: 8, alignItems: "end" }}
        aria-label="Filter personal review prompts"
      >
        <label style={{ display: "flex", flexDirection: "column", gap: 4, fontSize: 9, color: "var(--color-dim)" }}>
          role
          <select
            value={role}
            onChange={(event) => setRole(event.target.value as "" | Role)}
            data-testid="insights-role-filter"
            style={{ minWidth: 126, padding: "7px 8px", color: "var(--color-text)", background: "var(--color-deep)", border: "1px solid var(--color-line)", borderRadius: "var(--radius-sm)" }}
          >
            <option value="">All roles</option>
            {ROLE_OPTIONS.map((option) => (
              <option key={option} value={option}>
                {option}
              </option>
            ))}
          </select>
        </label>
        <label style={{ display: "flex", flexDirection: "column", gap: 4, fontSize: 9, color: "var(--color-dim)" }}>
          champion
          <input
            value={championInput}
            onChange={(event) => setChampionInput(event.target.value)}
            placeholder="All champions"
            data-testid="insights-champion-filter"
            style={{ minWidth: 150, padding: "7px 8px", color: "var(--color-text)", background: "var(--color-deep)", border: "1px solid var(--color-line)", borderRadius: "var(--radius-sm)" }}
          />
        </label>
        <button type="submit" className="pill" data-testid="insights-apply-filter">
          Apply filters
        </button>
      </form>

      {insights.isLoading && (
        <div role="status" aria-live="polite" style={{ color: "var(--color-dim)", fontSize: 10.5 }}>
          Loading local review prompts…
        </div>
      )}
      {insights.isError && (
        <div role="alert" data-testid="insights-error" style={{ color: "var(--color-amber)", fontSize: 10.5 }}>
          {classifyApiError(insights.error) === "offline"
            ? "The sidecar is offline. Review prompts will return when it reconnects."
            : "Personal History insights are unavailable. Try again after the active account is ready."}
        </div>
      )}
      {insights.data?.state === "empty" && (
        <div data-testid="insights-empty">
          <EmptyState
            title={Object.keys(filters).length ? "No matches for these filters" : "No Personal History yet"}
            body={
              Object.keys(filters).length
                ? "Change the role or champion filter; no population rows are substituted for this local sample."
                : "Start Backfill below to build a local review queue. Population evidence is not used here."
            }
          />
        </div>
      )}
      {insights.data?.state === "available" && (
        <>
          <div
            style={{ display: "flex", flexWrap: "wrap", gap: 8, alignItems: "center", color: "var(--color-dim)", fontSize: 10 }}
            data-testid="insights-sample-size"
          >
            <span className="mono-n" style={{ color: "var(--color-teal)" }}>
              {insights.data.sample_size.toLocaleString()} filtered matches
            </span>
            <span>·</span>
            <span>Filters apply before the review windows.</span>
          </div>
          <FeatureInsights
            insights={insights.data.feature_insights ?? []}
            trajectories={insights.data.feature_trajectories ?? []}
          />
          <div>
            <h3 className="route-subheading" style={{ marginBottom: 7 }}>
              Role profiles
            </h3>
            <ProfileTable testId="insights-role-table" title="Personal History by role" rows={insights.data.roles} />
          </div>
          <div>
            <h3 className="route-subheading" style={{ marginBottom: 7 }}>
              Champion profiles
            </h3>
            {insights.data.champions.length > 0 ? (
              <ProfileTable
                testId="insights-champion-table"
                title="Personal champion review prompts"
                rows={insights.data.champions}
              />
            ) : (
              <Unavailable reason="No champion rows in this filtered sample" />
            )}
          </div>
          <div>
            <h3 className="route-subheading" style={{ marginBottom: 7 }}>
              Latest versus preceding review queue
            </h3>
            <p style={{ margin: "0 0 8px", fontSize: 10, color: "var(--color-dim)" }}>
              No forecast: this noisy comparison only helps choose matches to inspect.
            </p>
            {windows ? (
              <div style={{ display: "flex", flexWrap: "wrap", gap: 8 }}>
                <ReviewQueue window={windows.latest} />
                <ReviewQueue window={windows.preceding} />
              </div>
            ) : (
              <Unavailable reason="review windows unavailable" />
            )}
          </div>
        </>
      )}
      <div style={{ fontSize: 9, color: "var(--color-dimmer)" }}>
        Source: local Personal History · no Findings Pack population fallback
      </div>
    </section>
  );
}
