import type { ChampSelectSessionView } from "./shared";

export function CompReadCard({ session }: { session: ChampSelectSessionView }) {
  const status = session.active ? `${session.pickedCount}/5 picked` : "Idle";
  const picks = session.knownAlliedPicks;

  return (
    <div
      className="card3"
      data-testid="card-comp-read"
      style={{ padding: 12, display: "flex", flexDirection: "column", gap: 9 }}
    >
      <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
        <span style={{ width: 6, height: 6, borderRadius: 999, background: session.active ? "var(--color-teal)" : "#7a8098" }} />
        <span style={{ font: "700 9.5px var(--font-mono)", letterSpacing: ".11em", color: "var(--color-dim)" }}>
          COMP READ
        </span>
        <span
          className="pill"
          style={{ marginLeft: "auto", background: "var(--color-surface-3)", color: "var(--color-dim)" }}
        >
          {status}
        </span>
      </div>
      {session.active ? (
        <>
          <div style={{ display: "flex", flexWrap: "wrap", gap: 6 }} data-testid="cs-comp-picks">
            {picks.length ? (
              picks.map((pick) => (
                <span
                  className="pill"
                  key={pick.cell_id}
                  style={{ background: "var(--color-surface-2)", color: "#cfd3e5" }}
                >
                  {pick.champion}
                </span>
              ))
            ) : (
              <span style={{ fontSize: 10, color: "var(--color-dim)" }}>No allied champion picks known.</span>
            )}
          </div>
          <p style={{ margin: "auto 0 0", fontSize: 10, lineHeight: 1.5, color: "#cfd3e5" }}>
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
