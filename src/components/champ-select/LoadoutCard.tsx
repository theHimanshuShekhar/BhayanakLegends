import type { ChampSelectSessionView, FindingsPackState } from "./shared";

export function LoadoutCard({
  session,
  packState,
}: {
  session: ChampSelectSessionView;
  packState: FindingsPackState;
}) {
  const context = session.localChampion
    ? `Session champion: ${session.localChampion}${session.locked ? " · locked" : " · not locked"}.`
    : session.active
      ? "Session champion is not selected."
      : "Waiting for a live session.";
  const guidance =
    packState === "loading"
      ? "Loading Findings Pack — champion-specific loadout guidance is not available yet."
      : packState === "error"
        ? "Unavailable: Findings Pack could not be loaded, so champion-specific loadout guidance is unavailable."
        : packState === "missing"
          ? "Unavailable: Findings Pack is missing, so champion-specific loadout guidance is unavailable."
          : "Unavailable: no exact champion-specific loadout finding exists.";

  return (
    <div className="card3" data-testid="card-loadout" style={{ padding: 12, display: "flex", flexDirection: "column", gap: 8 }}>
      <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
        <span style={{ width: 6, height: 6, borderRadius: 999, background: session.locked ? "var(--color-teal)" : "var(--color-accent)" }} />
        <span style={{ font: "700 9.5px var(--font-mono)", letterSpacing: ".11em", color: "var(--color-dim)" }}>
          LOADOUT · READ-ONLY
        </span>
      </div>
      <p style={{ margin: 0, padding: 9, borderRadius: 11, background: "var(--color-surface-2)", fontSize: 10, lineHeight: 1.5, color: "#cfd3e5" }}>
        {context}
      </p>
      <p
        style={{ margin: "auto 0 0", fontSize: 9, lineHeight: 1.4, color: "var(--color-dimmer)" }}
        data-testid="cs-loadout-unavailable"
        role="status"
      >
        {guidance}
      </p>
    </div>
  );
}
