import { useMemo } from "react";
import { useBenchmarks, useHistorySummary, usePack, useTrajectories } from "../api/hooks";
import { CaveatFooter } from "../components/journal/CaveatFooter";
import { patchOrder } from "../components/journal/format";
import { ProgressSummaryCard } from "../components/progress/ProgressSummaryCard";
import { RollingWrChart, type WrPoint } from "../components/progress/RollingWrChart";
import { BenchmarkCards } from "../components/progress/BenchmarkCards";
import { LeakPanel } from "../components/progress/LeakPanel";
import { WhatIfPanel } from "../components/progress/WhatIfPanel";
import { LeverAdoption } from "../components/progress/LeverAdoption";
import { LaneConversion } from "../components/progress/LaneConversion";

const LANE_CONVERSION_RE = /lane.*conversion|conversion.*lane/i;

export function ProgressPage() {
  const pack = usePack();
  const trajectories = useTrajectories();
  const benchmarks = useBenchmarks();
  const summary = useHistorySummary();

  const perPatch: WrPoint[] = useMemo(() => {
    const byPatch = new Map<string, { games: number; wins: number; weighted: number }>();
    for (const p of trajectories.data ?? []) {
      const cur = byPatch.get(p.patch) ?? { games: 0, wins: 0, weighted: 0 };
      cur.games += p.games;
      cur.wins += p.wins;
      cur.weighted += p.rolling_wr * p.games;
      byPatch.set(p.patch, cur);
    }
    return [...byPatch.entries()]
      .sort(([a], [b]) => patchOrder(a) - patchOrder(b))
      .map(([patch, agg]) => ({
        patch,
        games: agg.games,
        rolling_wr: agg.games > 0 ? agg.weighted / agg.games : 0,
      }));
  }, [trajectories.data]);

  const laneFinding =
    pack.data?.findings.find((f) => LANE_CONVERSION_RE.test(f.key)) ?? null;

  return (
    <div
      style={{
        display: "grid",
        gridTemplateColumns: "1fr 336px",
        gap: 16,
        paddingTop: 14,
        alignItems: "start",
      }}
    >
      <div style={{ display: "flex", flexDirection: "column", gap: 12, minWidth: 0 }}>
        <div style={{ display: "grid", gridTemplateColumns: "270px 1fr", gap: 14 }}>
          {summary.data && <ProgressSummaryCard summary={summary.data} />}
          <RollingWrChart points={perPatch} />
        </div>

        {benchmarks.isError && (
          <div style={{ fontSize: 10.5, color: "var(--color-danger)" }}>
            Benchmarks unavailable — sidecar offline.
          </div>
        )}
        {benchmarks.data && benchmarks.data.length > 0 && (
          <BenchmarkCards rows={benchmarks.data} />
        )}

        <div
          style={{
            display: "grid",
            gridTemplateColumns: "1fr 300px",
            gap: 14,
            alignItems: "stretch",
          }}
        >
          <LeakPanel />
          <WhatIfPanel />
        </div>

        {trajectories.isError && (
          <div style={{ fontSize: 10.5, color: "var(--color-danger)" }}>
            Trajectories unavailable — sidecar offline.
          </div>
        )}
      </div>

      <div style={{ display: "flex", flexDirection: "column", gap: 14, minWidth: 0 }}>
        <LeverAdoption habits={pack.data?.habits ?? []} />
        {pack.isLoading && (
          <div style={{ fontSize: 10.5, color: "var(--color-dim)" }}>loading…</div>
        )}
        {pack.isError && (
          <div style={{ fontSize: 10.5, color: "var(--color-danger)" }}>
            Findings Pack unavailable — sidecar offline.
          </div>
        )}
        {laneFinding && <LaneConversion finding={laneFinding} />}
        <CaveatFooter />
      </div>
    </div>
  );
}
