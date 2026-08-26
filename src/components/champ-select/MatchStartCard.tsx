import type { ChampSelectSessionView } from "./shared";

export function MatchStartCard({ session }: { session: ChampSelectSessionView }) {
  const { active, localChampion: pick, assignedRole: role, locked } = session;
  const status = locked
    ? `${pick ?? "Champion unavailable"} locked${role ? ` · ${role}` : ""}`
    : pick
      ? `${pick} picked — not locked`
      : role
        ? `${role} assigned — choose a pick in the client`
        : active
          ? "Assigned role pending — choose a pick in the client"
          : "Waiting for a live session";

  return (
    <div
      className="card3"
      data-testid="cs-match-start"
      style={{ padding: 12, flex: 1, minHeight: 0, display: "flex", flexDirection: "column", gap: 8 }}
    >
      <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
        <span
          style={{
            width: 6,
            height: 6,
            borderRadius: 999,
            background: locked ? "var(--color-teal)" : active ? "var(--color-amber)" : "#3f4459",
          }}
        />
        <span style={{ font: "700 9.5px var(--font-mono)", letterSpacing: ".11em", color: "var(--color-dim)" }}>
          AT MATCH START
        </span>
      </div>
      <div
        data-testid="cs-session-status"
        style={{
          display: "flex",
          alignItems: "center",
          gap: 9,
          padding: 9,
          borderRadius: 12,
          background: "var(--color-surface-2)",
          boxShadow: "var(--shadow-z1)",
        }}
      >
        <span
          style={{
            width: 8,
            height: 8,
            borderRadius: 999,
            background: locked ? "var(--color-teal)" : active ? "var(--color-amber)" : "#3f4459",
            boxShadow: locked ? "0 0 8px var(--color-teal)" : "none",
            flex: "none",
          }}
        />
        <div style={{ fontSize: 10, lineHeight: 1.4, color: "var(--color-dim)" }}>
          <b style={{ color: "#cfd3e5" }}>{status}.</b>{" "}
          {locked
            ? "Suggestions and lock prompts are complete for this local cell."
            : "The companion mirrors the League client; completion remains pending until the lock evidence arrives."}
        </div>
      </div>
      <div
        style={{
          display: "flex",
          alignItems: "center",
          gap: 9,
          padding: 9,
          borderRadius: 12,
          background: "var(--color-surface-2)",
          boxShadow: "var(--shadow-z1)",
        }}
      >
        <span style={{ width: 8, height: 8, borderRadius: 999, background: "#3f4459", flex: "none" }} />
        <div style={{ fontSize: 10, lineHeight: 1.4, color: "var(--color-dim)" }}>
          Bans lock, roles finalize and the loading screen starts the moment the last pick locks.
        </div>
      </div>
      {!locked && (
        <div style={{ marginTop: "auto", display: "flex", flexDirection: "column", gap: 7 }}>
          <button
            type="button"
            disabled
            data-testid="cs-lock-button"
            title="Locking happens in the League client — this panel mirrors the session."
            style={{
              padding: "10px 12px",
              borderRadius: 999,
              border: "none",
              background: "var(--color-surface-3)",
              color: "var(--color-dim)",
              font: "700 11px var(--font-mono)",
              textAlign: "center",
              cursor: "not-allowed",
            }}
          >
            {pick ? `Lock ${pick} in the client` : "Choose a pick in the client"}
          </button>
        </div>
      )}
    </div>
  );
}
