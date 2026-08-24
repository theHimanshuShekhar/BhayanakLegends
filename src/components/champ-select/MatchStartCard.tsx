export function MatchStartCard({ active, pick }: { active: boolean; pick?: string }) {
  return (
    <div
      className="card3"
      data-testid="cs-match-start"
      style={{ padding: 12, flex: 1, minHeight: 0, display: "flex", flexDirection: "column", gap: 8 }}
    >
      <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
        <span style={{ width: 6, height: 6, borderRadius: 999, background: "#3f4459" }} />
        <span style={{ font: "700 9.5px var(--font-mono)", letterSpacing: ".11em", color: "var(--color-dim)" }}>
          AT MATCH START
        </span>
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
          <b style={{ color: "#cfd3e5" }}>:2999 comes online.</b> Live loadout, event feed and win probability start
          updating.
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
      <div style={{ marginTop: "auto", display: "flex", flexDirection: "column", gap: 7 }}>
        <button
          type="button"
          disabled={!active}
          data-testid="cs-lock-button"
          title={active ? undefined : "Locking arrives with the live client link"}
          style={{
            padding: "10px 12px",
            borderRadius: 999,
            border: "none",
            background: "var(--color-accent)",
            color: "#0e1020",
            font: "700 12px var(--font-mono)",
            textAlign: "center",
            boxShadow: "0 4px 0 var(--color-accent-low),0 14px 24px -8px rgba(145,132,217,.6)",
            opacity: active ? undefined : 0.55,
            cursor: active ? "pointer" : "not-allowed",
          }}
        >
          Lock {pick ?? "your pick"}
        </button>
      </div>
    </div>
  );
}
