import type { ChampSelectSessionView, FindingsPackState } from "./shared";
import { Dot, SectionHead } from "../ui";

export function HowToPlayCard({
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
      ? "Loading… Findings Pack — champion-specific gameplan guidance is not available."
      : packState === "error"
        ? "Unavailable: Findings Pack could not be loaded, so champion-specific gameplan guidance is unavailable."
        : packState === "missing"
          ? "Unavailable: Findings Pack is missing, so champion-specific gameplan guidance is unavailable."
          : "Unavailable: no exact champion-specific gameplan finding exists.";

  return (
    <div
      className="card3"
      data-testid="card-how-to-play"
      style={{ padding: 12, flex: 1, minHeight: 0, display: "flex", flexDirection: "column", gap: 8 }}
    >
      <SectionHead label="HOW TO PLAY IT" color={session.locked ? "var(--color-teal)" : "var(--color-dimmer)"} />
      <div
        style={{
          display: "flex",
          gap: 9,
          padding: 9,
          borderRadius: 13,
          background: "var(--color-surface-2)",
          boxShadow: "var(--shadow-z1)",
        }}
      >
        <p style={{ margin: 0, fontSize: 11, lineHeight: 1.5, color: "var(--color-soft-text)" }}>{context}</p>
      </div>
      <div
        role="status"
        style={{
          marginTop: "auto",
          display: "flex",
          alignItems: "center",
          gap: 9,
          padding: "9px 10px",
          borderRadius: 13,
          background: "var(--color-surface-2)",
          boxShadow: "var(--shadow-z1)",
        }}
      >
        <Dot color="var(--color-dimmer)" />
        <div style={{ fontSize: 9.5, lineHeight: 1.4, color: "var(--color-dim)" }}>{guidance}</div>
      </div>
    </div>
  );
}
