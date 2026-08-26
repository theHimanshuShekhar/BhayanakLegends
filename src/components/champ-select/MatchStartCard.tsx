import type { ChampSelectSessionView } from "./shared";
import { Dot, SectionHead } from "../ui";

export function MatchStartCard({ session }: { session: ChampSelectSessionView }) {
  const { active, localChampion: pick, assignedRole: role, locked } = session;
  const status = locked
    ? `${pick ?? "Champion unavailable"} locked${role ? ` · ${role}` : ""}`
    : pick
      ? `${pick} picked — not locked`
      : role
        ? `${role} assigned — choose a pick in the client`
        : active
          ? "The League client has not reported an assigned role — choose a pick in the client"
          : "Waiting for a live session";

  return (
    <div
      className="card3"
      data-testid="cs-match-start"
      style={{ padding: 12, flex: 1, minHeight: 0, display: "flex", flexDirection: "column", gap: 8 }}
    >
      <SectionHead
        label="AT MATCH START"
        color={locked ? "var(--color-teal)" : active ? "var(--color-amber)" : "var(--color-dimmer)"}
      />
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
        <Dot
          color={locked ? "var(--color-teal)" : active ? "var(--color-amber)" : "var(--color-dimmer)"}
          glow={locked}
        />
        <div style={{ fontSize: 10, lineHeight: 1.4, color: "var(--color-dim)" }}>
          <b style={{ color: "var(--color-soft-text)" }}>{status}.</b>{" "}
          {locked
            ? "Suggestions and lock prompts are complete for this local cell."
            : "Lock evidence has not been received from the League client."}
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
        <Dot color="var(--color-dimmer)" />
        <div style={{ fontSize: 10, lineHeight: 1.4, color: "var(--color-dim)" }}>
          Bans lock, roles finalize and the loading screen starts the moment the last pick locks.
        </div>
      </div>
      {!locked && (
        <div
          data-testid="cs-lock-status"
          role="status"
          style={{
            marginTop: "auto",
            padding: "10px 12px",
            borderRadius: 12,
            background: "var(--color-surface-3)",
            color: "var(--color-dim)",
            fontSize: 10,
            lineHeight: 1.4,
          }}
        >
          {pick ? `Lock ${pick} in the League client.` : "Choose a pick in the League client."} This panel mirrors the session and cannot lock it.
        </div>
      )}
    </div>
  );
}
