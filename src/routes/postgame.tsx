import { usePack, usePostgameLatest } from "../api/hooks";
import { actionableErrorMessage } from "../api/client";
import {
  CheckpointStrip,
  ComebackOddsCard,
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
      {query.isError && (
        <div style={{ marginBottom: 10, fontSize: 11, color: "var(--color-amber)" }}>
          {actionableErrorMessage(query.error)}
        </div>
      )}
      {packQuery.isError && (
        <div style={{ marginBottom: 10, fontSize: 11, color: "var(--color-amber)" }}>
          {actionableErrorMessage(packQuery.error, "pack")}
        </div>
      )}

      <VerdictHeader digest={digest} />
      <CheckpointStrip digest={digest} />

      {digest == null && (
        <div
          className="card3b"
          data-testid="empty-state"
          style={{ marginTop: 12, padding: 14, textAlign: "center", fontSize: 11, color: "var(--color-dim)" }}
        >
          No games analyzed yet — Backfill from History
        </div>
      )}

      <div
        style={{
          flex: 1,
          display: "grid",
          gridTemplateColumns: "1fr 380px",
          gap: 14,
          paddingTop: 14,
          minHeight: 0,
        }}
      >
        <div style={{ display: "flex", flexDirection: "column", gap: 12, minHeight: 0 }}>
          <HabitsCard digest={digest} />
          <section className="card3" style={{ padding: 13, display: "flex", alignItems: "center", gap: 10 }}>
            <span
              className="pill"
              style={{ background: "var(--color-amber-low)", color: "var(--color-amber)" }}
            >
              Backfill
            </span>
            <p style={{ margin: 0, fontSize: 10.5, lineHeight: 1.5, color: "#cfd3e5" }}>
              Older games arrive through Backfill — start it from the History tab. This digest covers
              the latest game only.
            </p>
          </section>
        </div>

        <div style={{ display: "flex", flexDirection: "column", gap: 12, minHeight: 0 }}>
          <ObjectiveReadCard pack={packQuery.data} />
          <ComebackOddsCard digest={digest} pack={packQuery.data} />
          <SurrenderReadCard />
        </div>
      </div>
    </div>
  );
}
