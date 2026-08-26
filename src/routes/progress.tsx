import { useBenchmarks, useHistorySummary, usePack, usePatchAggregates } from "../api/hooks";
import { actionableErrorMessage } from "../api/client";
import { CaveatFooter } from "../components/journal/CaveatFooter";
import { ProgressSummaryCard } from "../components/progress/ProgressSummaryCard";
import { RollingWrChart } from "../components/progress/RollingWrChart";
import { BenchmarkCards } from "../components/progress/BenchmarkCards";
import { LeakPanel } from "../components/progress/LeakPanel";
import { WhatIfPanel } from "../components/progress/WhatIfPanel";
import { LeverAdoption } from "../components/progress/LeverAdoption";
import { LaneConversion } from "../components/progress/LaneConversion";
import { PageHeader } from "../components/Layout";

const LANE_CONVERSION_RE = /lane.*conversion|conversion.*lane/i;

function ProgressSkeleton() {
  return (
    <div aria-hidden="true" className="history-skeletons">
      <span />
      <span />
    </div>
  );
}

export function ProgressPage() {
  const pack = usePack();
  const aggregates = usePatchAggregates();
  const benchmarks = useBenchmarks();
  const summary = useHistorySummary();

  const perPatch = aggregates.data ?? [];
  const laneFinding =
    pack.data?.findings.find((f) => LANE_CONVERSION_RE.test(f.key)) ?? null;

  return (
    <div className="progress-page">
      <PageHeader title="Trajectory" />
      <div className="progress-layout">
        <main className="progress-main">
          <div className="progress-pair">
            <section aria-labelledby="personal-history-trajectory-heading">
              <h2 id="personal-history-trajectory-heading" className="route-panel-heading">
                Personal History
              </h2>
              {summary.data ? (
                <ProgressSummaryCard summary={summary.data} />
              ) : (
                <p role="status" aria-live="polite" style={{ margin: 0, fontSize: 10.5, color: "var(--color-dim)" }}>
                  Loading Personal History summary
                </p>
              )}
            </section>
            <section aria-labelledby="patch-win-rate-heading">
              <h2 id="patch-win-rate-heading" className="route-panel-heading">
                Patch win rate
              </h2>
              <RollingWrChart points={perPatch} />
            </section>
          </div>

          <section aria-labelledby="benchmarks-heading">
            <h2 id="benchmarks-heading" className="route-panel-heading">
              Benchmarks
            </h2>
            {benchmarks.isError && (
              <div role="alert" style={{ fontSize: 10.5, color: "var(--color-danger)" }}>
                {actionableErrorMessage(benchmarks.error)}
              </div>
            )}
            {benchmarks.data && benchmarks.data.length > 0 && <BenchmarkCards rows={benchmarks.data} />}
            {benchmarks.data && benchmarks.data.length === 0 && !benchmarks.isError && (
              <div data-testid="benchmarks-empty" style={{ fontSize: 10.5, color: "var(--color-dimmer)" }}>
                Benchmarks arrive once Backfill fills Personal History for a role.
              </div>
            )}
          </section>

          <div className="progress-pair">
            <section aria-labelledby="deaths-heading">
              <h2 id="deaths-heading" className="route-panel-heading">
                Deaths by game minute
              </h2>
              <LeakPanel />
            </section>
            <section aria-labelledby="what-if-heading">
              <h2 id="what-if-heading" className="route-panel-heading">
                What-if simulator
              </h2>
              <WhatIfPanel />
            </section>
          </div>

          {aggregates.isError && (
            <div role="alert" style={{ fontSize: 10.5, color: "var(--color-danger)" }}>
              {actionableErrorMessage(aggregates.error)}
            </div>
          )}
        </main>

        <aside className="progress-rail">
          <section aria-labelledby="lever-adoption-heading">
            <h2 id="lever-adoption-heading" className="route-panel-heading">
              Lever adoption
            </h2>
            <LeverAdoption habits={pack.data?.habits ?? []} />
            {pack.isLoading && (
              <>
                <ProgressSkeleton />
                <div role="status" aria-live="polite" className="sr-only">
                  Loading findings pack
                </div>
              </>
            )}
            {pack.isError && (
              <div role="alert" style={{ fontSize: 10.5, color: "var(--color-danger)" }}>
                {actionableErrorMessage(pack.error, "pack")}
              </div>
            )}
          </section>
          {laneFinding && (
            <section aria-labelledby="lane-conversion-heading">
              <h2 id="lane-conversion-heading" className="route-panel-heading">
                Lane conversion
              </h2>
              <LaneConversion finding={laneFinding} />
            </section>
          )}
          <CaveatFooter />
        </aside>
      </div>
    </div>
  );
}
