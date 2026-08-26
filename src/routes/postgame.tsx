import { usePack, usePostgameLatest } from "../api/hooks";
import { actionableErrorMessage } from "../api/client";
import {
  CheckpointStrip,
  ComebackOddsCard,
  EmptyState,
  HabitsCard,
  ObjectiveReadCard,
  SurrenderReadCard,
  VerdictHeader,
} from "../components/postgame";
import { PageHeader } from "../components/Layout";

export function PostGamePage() {
  const query = usePostgameLatest();
  const packQuery = usePack();
  const digest = query.data ?? null;

  return (
    <div
      style={{
        margin: "0 -14px -14px",
        padding: "12px 14px 14px",
        minHeight: "100%",
        display: "flex",
        flexDirection: "column",
        background: "radial-gradient(120% 80% at 20% 0%,#2a1520,var(--color-bg) 55%)",
      }}
    >
      <PageHeader kicker="post-game review · the 30 seconds after the game" title="Post-game Review" />
      {(query.isLoading || packQuery.isLoading) && (
        <div role="status" aria-live="polite" style={{ minHeight: 15, fontSize: 10.5, color: "var(--color-dim)" }}>
          Loading post-game review…
        </div>
      )}
      <section
        className="postgame-evidence"
        aria-label="Post-game evidence"
        aria-busy={query.isLoading || packQuery.isLoading}
      >
        {query.isError && (
          <div role="alert" style={{ marginBottom: 10, fontSize: 11, color: "var(--color-amber)" }}>
            {actionableErrorMessage(query.error)}
          </div>
        )}
        {packQuery.isError && (
          <div role="alert" style={{ marginBottom: 10, fontSize: 11, color: "var(--color-amber)" }}>
            {actionableErrorMessage(packQuery.error, "pack")}
          </div>
        )}

        <VerdictHeader digest={digest} />
        <CheckpointStrip digest={digest} />

        {digest == null && !query.isLoading && (
          <div style={{ marginTop: 12 }}>
            <EmptyState title="No digest yet" body="No games analyzed yet — Backfill from History" />
          </div>
        )}

        <div className="postgame-route-grid">
          <div className="postgame-main-column">
            <HabitsCard digest={digest} />
            <section className="card3" aria-labelledby="postgame-backfill-heading" style={{ padding: 13, display: "flex", alignItems: "center", gap: 10 }}>
              <h2
                id="postgame-backfill-heading"
                style={{ margin: 0, font: "600 10.5px var(--font-mono)", color: "var(--color-amber)" }}
              >
                Backfill context
              </h2>
              <p style={{ margin: 0, fontSize: 10.5, lineHeight: 1.5, color: "#cfd3e5" }}>
                Older games arrive through Backfill — start it from the History tab. This digest covers
                the latest game only.
              </p>
            </section>
          </div>

          <div className="postgame-support-column">
            <ObjectiveReadCard pack={packQuery.data} />
            <ComebackOddsCard digest={digest} pack={packQuery.data} />
            <SurrenderReadCard />
          </div>
        </div>
      </section>
    </div>
  );
}
