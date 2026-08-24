import { useHistorySummary } from "../api/hooks";
import "../components/journal/kicker.css";
import { PageHeader } from "../components/Layout";
import { CaveatFooter } from "../components/journal/CaveatFooter";
import { SyncPanel } from "../components/journal/SyncPanel";
import { Card, Stat, pct } from "../components/ui";

export function HistoryPage() {
  const summary = useHistorySummary();

  return (
    <div>
      <PageHeader kicker="Improvement Journal" title="History" />

      <div className="max-w-3xl space-y-4">
        <Card kicker="Personal History" title="What's on this machine">
          {summary.isLoading && <div className="text-xs text-dim">loading…</div>}
          {summary.isError && (
            <div className="text-xs text-danger">
              No local shards found — start a Backfill below or import a folder.
            </div>
          )}
          {summary.data && (
            <>
              <div className="flex flex-wrap gap-8" data-testid="summary-stats">
                <Stat
                  label="Matches"
                  value={<span data-testid="summary-matches">{summary.data.matches.toLocaleString()}</span>}
                />
                <Stat label="Win rate" value={pct(summary.data.win_rate)} />
                <Stat
                  label="Patches"
                  value={
                    summary.data.patches.length > 0
                      ? `${summary.data.patches[0]} → ${summary.data.patches[summary.data.patches.length - 1]}`
                      : "—"
                  }
                />
              </div>

              {summary.data.by_role.length > 0 && (
                <table className="mt-4 w-full text-left font-mono text-xs" data-testid="by-role-table">
                  <thead>
                    <tr className="text-[10px] uppercase tracking-widest text-dimmer">
                      <th className="py-1 font-medium">role</th>
                      <th className="py-1 font-medium">games</th>
                      <th className="py-1 font-medium">wins</th>
                      <th className="py-1 font-medium">wr</th>
                    </tr>
                  </thead>
                  <tbody>
                    {summary.data.by_role.map((r) => (
                      <tr key={r.role} className="border-t border-line">
                        <td className="py-1">{r.role}</td>
                        <td className="py-1 text-dim">{r.games}</td>
                        <td className="py-1 text-dim">{r.wins}</td>
                        <td className="py-1">{r.games > 0 ? pct(r.wins / r.games) : "—"}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              )}
            </>
          )}
        </Card>

        <SyncPanel />

        <CaveatFooter />
      </div>
    </div>
  );
}
