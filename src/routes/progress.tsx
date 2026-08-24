import { useMemo, useState } from "react";
import { useHistorySummary, useTrajectories } from "../api/hooks";
import "../components/journal/kicker.css";
import { PageHeader } from "../components/Layout";
import { CaveatFooter } from "../components/journal/CaveatFooter";
import { patchOrder } from "../components/journal/format";
import { TrendChart, type TrendPoint } from "../components/journal/TrendChart";
import { Card, EmptyState, pct } from "../components/ui";

function Chip({
  active,
  onClick,
  children,
  testid,
}: {
  active: boolean;
  onClick: () => void;
  children: string;
  testid: string;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      data-testid={testid}
      className={`rounded-full border px-3 py-1 text-[10px] font-medium uppercase tracking-widest transition-colors ${
        active
          ? "border-accent bg-accent-low text-accent"
          : "border-line text-dim hover:border-dim hover:text-text"
      }`}
    >
      {children}
    </button>
  );
}

export function ProgressPage() {
  const trajectories = useTrajectories();
  const summary = useHistorySummary();
  const [role, setRole] = useState<string>("ALL");

  const roles = useMemo(() => {
    const set = new Set<string>();
    for (const p of trajectories.data ?? []) set.add(p.role);
    return [...set].sort();
  }, [trajectories.data]);

  const filtered = useMemo(() => {
    const all = trajectories.data ?? [];
    return role === "ALL" ? all : all.filter((p) => p.role === role);
  }, [trajectories.data, role]);

  const perPatch = useMemo(() => {
    const byPath = new Map<string, { games: number; wins: number; wrWeighted: number }>();
    for (const p of filtered) {
      const cur = byPath.get(p.patch) ?? { games: 0, wins: 0, wrWeighted: 0 };
      cur.games += p.games;
      cur.wins += p.wins;
      cur.wrWeighted += p.rolling_wr * p.games;
      byPath.set(p.patch, cur);
    }
    return [...byPath.entries()]
      .sort(([a], [b]) => patchOrder(a) - patchOrder(b))
      .map(([patch, agg]) => ({
        patch,
        games: agg.games,
        wins: agg.wins,
        rolling_wr: agg.games > 0 ? agg.wrWeighted / agg.games : 0,
      }));
  }, [filtered]);

  const trend: TrendPoint[] = perPatch.map((row) => ({ label: row.patch, value: row.rolling_wr }));

  return (
    <div>
      <PageHeader kicker="Improvement Journal" title="Progress" />

      {summary.data && (
        <div className="mb-4 flex gap-6 font-mono text-xs text-dim">
          <span>
            <span className="text-dimmer">matches </span>
            {summary.data.matches.toLocaleString()}
          </span>
          <span>
            <span className="text-dimmer">win rate </span>
            {pct(summary.data.win_rate)}
          </span>
          {summary.data.patches.length > 0 && (
            <span>
              <span className="text-dimmer">patches </span>
              {summary.data.patches[0]} → {summary.data.patches[summary.data.patches.length - 1]}
            </span>
          )}
        </div>
      )}

      <div className="mb-4 flex flex-wrap gap-2" data-testid="role-chips">
        <Chip active={role === "ALL"} onClick={() => setRole("ALL")} testid="role-ALL">
          All
        </Chip>
        {roles.map((r) => (
          <Chip key={r} active={role === r} onClick={() => setRole(r)} testid={`role-${r}`}>
            {r}
          </Chip>
        ))}
      </div>

      {trajectories.isLoading && <div className="text-xs text-dim">loading…</div>}
      {trajectories.isError && (
        <div className="text-xs text-danger">Trajectories unavailable — sidecar offline.</div>
      )}
      {!trajectories.isLoading && !trajectories.isError && perPatch.length === 0 && (
        <EmptyState
          title="No tracked games yet"
          body="Once Backfill downloads matches from the History tab, your win-rate trend per patch shows up here."
        />
      )}

      {perPatch.length > 0 && (
        <Card kicker="Trajectory" title="Rolling win rate per patch">
          <TrendChart points={trend} />
          <table className="mt-3 w-full text-left font-mono text-xs" data-testid="patch-table">
            <thead>
              <tr className="text-[10px] uppercase tracking-widest text-dimmer">
                <th className="py-1 font-medium">patch</th>
                <th className="py-1 font-medium">games</th>
                <th className="py-1 font-medium">wins</th>
                <th className="py-1 font-medium">rolling wr</th>
              </tr>
            </thead>
            <tbody>
              {perPatch.map((row) => (
                <tr key={row.patch} className="border-t border-line">
                  <td className="py-1">{row.patch}</td>
                  <td className="py-1 text-dim">{row.games}</td>
                  <td className="py-1 text-dim">{row.wins}</td>
                  <td className="py-1">{pct(row.rolling_wr)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </Card>
      )}

      <div className="mt-4">
        <CaveatFooter />
      </div>
    </div>
  );
}
