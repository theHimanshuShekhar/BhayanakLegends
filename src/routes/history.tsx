import { useHistorySummary } from "../api/hooks";
import { CaveatFooter } from "../components/journal/CaveatFooter";
import { SyncPanel } from "../components/journal/SyncPanel";
import { pct } from "../components/ui";

function StatCell({
  label,
  value,
  testid,
}: {
  label: string;
  value: string;
  testid?: string;
}) {
  return (
    <div className="card3" style={{ padding: 11, flex: 1, minWidth: 0 }}>
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

export function HistoryPage() {
  const summary = useHistorySummary();

  return (
    <div
      style={{
        display: "flex",
        flexDirection: "column",
        gap: 14,
        paddingTop: 14,
        maxWidth: 860,
      }}
    >
      <div
        className="card3b"
        style={{ padding: 14, display: "flex", flexDirection: "column", gap: 10 }}
      >
        <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", gap: 8 }}>
          <span className="kicker">PERSONAL HISTORY · THIS MACHINE</span>
          {summary.data && (
            <span className="mono-n" style={{ fontSize: 10, color: "var(--color-teal)" }}>
              {summary.data.matches.toLocaleString()} synced
            </span>
          )}
        </div>

        {summary.isLoading && (
          <div style={{ fontSize: 10.5, color: "var(--color-dim)" }}>loading…</div>
        )}
        {summary.isError && (
          <div style={{ fontSize: 10.5, color: "var(--color-danger)" }}>
            No local shards found — start a Backfill below or import a folder.
          </div>
        )}

        {summary.data && (
          <>
            <div
              style={{ display: "flex", gap: 10, alignItems: "stretch" }}
              data-testid="summary-stats"
            >
              <StatCell
                label="Matches"
                value={summary.data.matches.toLocaleString()}
                testid="summary-matches"
              />
              <StatCell label="Win rate" value={pct(summary.data.win_rate)} />
              <StatCell
                label="Patches"
                value={
                  summary.data.patches.length > 0
                    ? `${summary.data.patches[0]} → ${summary.data.patches[summary.data.patches.length - 1]}`
                    : "—"
                }
              />
            </div>

            {summary.data.by_role.length > 0 && (
              <table
                className="mono-n w-full text-left"
                style={{ fontSize: 11, borderCollapse: "collapse" }}
                data-testid="by-role-table"
              >
                <thead>
                  <tr
                    style={{
                      fontSize: 9,
                      letterSpacing: ".08em",
                      textTransform: "uppercase",
                      color: "var(--color-dimmer)",
                    }}
                  >
                    <th style={{ padding: "4px 0", fontWeight: 400 }}>role</th>
                    <th style={{ padding: "4px 0", fontWeight: 400 }}>games</th>
                    <th style={{ padding: "4px 0", fontWeight: 400 }}>wins</th>
                    <th style={{ padding: "4px 0", fontWeight: 400 }}>wr</th>
                  </tr>
                </thead>
                <tbody>
                  {summary.data.by_role.map((r) => (
                    <tr key={r.role} style={{ borderTop: "1px solid var(--color-line)" }}>
                      <td style={{ padding: "5px 0" }}>{r.role}</td>
                      <td style={{ padding: "5px 0", color: "var(--color-dim)" }}>{r.games}</td>
                      <td style={{ padding: "5px 0", color: "var(--color-dim)" }}>{r.wins}</td>
                      <td style={{ padding: "5px 0" }}>
                        {r.games > 0 ? pct(r.wins / r.games) : "—"}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
          </>
        )}
      </div>

      <SyncPanel />

      <CaveatFooter />
    </div>
  );
}
