import { useHistorySummary } from "../api/hooks";
import { classifyApiError } from "../api/client";
import { CaveatFooter } from "../components/journal/CaveatFooter";
import { SyncPanel } from "../components/journal/SyncPanel";
import { Unavailable } from "../components/ui";
import { formatRate as pct } from "../components/format";
import { PageHeader } from "../components/Layout";
import type { ReactNode } from "react";

function StatCell({
  label,
  value,
  testid,
}: {
  label: string;
  value: ReactNode;
  testid?: string;
}) {
  return (
    <div className="card3" style={{ padding: 11, flex: "1 1 180px", minWidth: 0 }}>
      <div
        style={{
          fontSize: 9,
          letterSpacing: ".08em",
          textTransform: "uppercase",
          color: "var(--color-dimmer)",
        }}
      >
        {label}
      </div>
      <div
        className="mono-n"
        style={{ font: "700 16px var(--font-mono)", marginTop: 4 }}
        data-testid={testid}
      >
        {value}
      </div>
    </div>
  );
}

function HistorySkeleton() {
  return (
    <div aria-hidden="true" className="history-skeletons">
      <span />
      <span />
      <span />
    </div>
  );
}

export function HistoryPage() {
  const summary = useHistorySummary();

  return (
    <div className="history-page">
      <PageHeader title="Improvement Journal" />
      <section
        className="card3b"
        aria-labelledby="personal-history-heading"
        aria-busy={summary.isLoading}
        style={{ padding: 14, display: "flex", flexDirection: "column", gap: 10 }}
      >
        <h2 id="personal-history-heading" className="route-panel-heading">
          Personal History
        </h2>
        <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", gap: 8 }}>
          <span className="kicker">PERSONAL HISTORY · THIS MACHINE</span>
          {summary.data && (
            <span className="mono-n" style={{ fontSize: 10, color: "var(--color-teal)" }}>
              {summary.data.matches.toLocaleString()} synced
            </span>
          )}
        </div>

        {summary.isLoading && (
          <>
            <HistorySkeleton />
            <div role="status" aria-live="polite" className="sr-only">
              Loading personal history
            </div>
          </>
        )}
        {summary.isError && (
          <div
            data-testid="summary-error"
            role="alert"
            style={{
              fontSize: 10.5,
              color:
                classifyApiError(summary.error) === "offline"
                  ? "var(--color-danger)"
                  : "var(--color-amber)",
            }}
          >
            {classifyApiError(summary.error) === "offline"
              ? "The sidecar is offline. Reopen the app and try again."
              : "No local shards found — start a Backfill below or import a folder."}
          </div>
        )}

        {summary.data && (
          <>
            <h3 className="route-subheading">Summary</h3>
            <div
              style={{ display: "flex", flexWrap: "wrap", gap: 10, alignItems: "stretch" }}
              data-testid="summary-stats"
            >
              <StatCell
                label="Matches"
                value={summary.data.matches.toLocaleString()}
                testid="summary-matches"
              />
              <StatCell
                label="Win rate"
                value={
                  summary.data.matches === 0 || summary.data.win_rate == null ? (
                    <Unavailable testId="summary-win-rate" reason="No games tracked yet" />
                  ) : (
                    pct(summary.data.win_rate)
                  )
                }
              />
              <StatCell
                label="Patches"
                value={
                  summary.data.patches.length > 0 ? (
                    `${summary.data.patches[0]} → ${summary.data.patches[summary.data.patches.length - 1]}`
                  ) : (
                    <Unavailable testId="summary-patches" reason="No patches in history" />
                  )
                }
              />
            </div>

            {summary.data.by_role.length > 0 && (
              <>
                <h3 className="route-subheading">By role</h3>
                <div className="table-scroll" role="region" aria-label="Personal history by role table">
                  <table
                    className="mono-n w-full text-left"
                    style={{ fontSize: 11, borderCollapse: "collapse" }}
                    data-testid="by-role-table"
                  >
                    <caption>Personal history by role</caption>
                    <thead>
                      <tr
                        style={{
                          fontSize: 9,
                          letterSpacing: ".08em",
                          textTransform: "uppercase",
                          color: "var(--color-dimmer)",
                        }}
                      >
                        <th scope="col" style={{ padding: "4px 0", fontWeight: 400 }}>
                          role
                        </th>
                        <th scope="col" style={{ padding: "4px 0", fontWeight: 400 }}>
                          games
                        </th>
                        <th scope="col" style={{ padding: "4px 0", fontWeight: 400 }}>
                          wins
                        </th>
                        <th scope="col" style={{ padding: "4px 0", fontWeight: 400 }}>
                          wr
                        </th>
                      </tr>
                    </thead>
                    <tbody>
                      {summary.data.by_role.map((r) => (
                        <tr key={r.role} style={{ borderTop: "1px solid var(--color-line)" }}>
                          <th scope="row" style={{ padding: "5px 0", textAlign: "left", fontWeight: 400 }}>
                            {r.role}
                          </th>
                          <td style={{ padding: "5px 0", color: "var(--color-dim)" }}>{r.games}</td>
                          <td style={{ padding: "5px 0", color: "var(--color-dim)" }}>{r.wins}</td>
                          <td style={{ padding: "5px 0" }}>
                            {r.games > 0 ? pct(r.wins / r.games) : <Unavailable reason="No games in this role" />}
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </>
            )}
          </>
        )}
      </section>

      <SyncPanel />

      <CaveatFooter />
    </div>
  );
}
