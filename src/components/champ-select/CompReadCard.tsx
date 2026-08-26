import type { ChampSelectSessionView } from "./shared";
import { SectionHead } from "../ui";

export function CompReadCard({ session }: { session: ChampSelectSessionView }) {
  const status = session.active ? `${session.pickedCount}/5 picked` : "Idle";
  const picks = session.knownAlliedPicks;

  return (
    <div
      className="card3"
      data-testid="card-comp-read"
      style={{ padding: 12, display: "flex", flexDirection: "column", gap: 9 }}
    >
      <SectionHead
        label="COMP READ"
        color={session.active ? "var(--color-teal)" : "var(--color-dimmer)"}
        right={
          <span className="pill" style={{ background: "var(--color-surface-3)", color: "var(--color-dim)" }}>
            {status}
          </span>
        }
      />
      {session.active ? (
        <>
          <div style={{ display: "flex", flexWrap: "wrap", gap: 6 }} data-testid="cs-comp-picks">
            {picks.length ? (
              picks.map((pick) => (
                <span
                  className="pill"
                  key={pick.cell_id}
                  style={{ background: "var(--color-surface-2)", color: "var(--color-soft-text)" }}
                >
                  {pick.champion}
                </span>
              ))
            ) : (
              <span style={{ fontSize: 10, color: "var(--color-dim)" }}>No allied champion picks known.</span>
            )}
          </div>
          <p style={{ margin: "auto 0 0", fontSize: 10, lineHeight: 1.5, color: "var(--color-soft-text)" }}>
            Live Companion session facts only.
          </p>
        </>
      ) : (
        <p style={{ margin: "auto 0 0", fontSize: 10, lineHeight: 1.5, color: "var(--color-dim)" }}>
          Waiting for a live session.
        </p>
      )}
    </div>
  );
}
