import type { InGameSnapshot, PlayerLive } from "../../api/types";
import { Dot } from "./bits";

const SKELETON_ROWS = 3;

function DashCell() {
  return (
    <div
      style={{
        flex: 1,
        padding: "7px 8px",
        borderRadius: 13,
        background: "var(--color-surface-3)",
        boxShadow: "var(--shadow-z1)",
        display: "flex",
        justifyContent: "space-between",
        alignItems: "center",
      }}
    >
      {["—", "—", "—", "—"].map((d, i) => (
        <span key={i} className="mono-n" style={{ fontSize: 9, color: "var(--color-dimmer)" }}>
          {d}
        </span>
      ))}
    </div>
  );
}

function SkeletonSide() {
  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
      {Array.from({ length: SKELETON_ROWS }, (_, row) => (
        <div key={row} style={{ display: "flex", gap: 6 }}>
          {Array.from({ length: 5 }, (_, cell) => (
            <DashCell key={cell} />
          ))}
        </div>
      ))}
    </div>
  );
}

const CELL_STYLE = {
  font: "700 9px var(--font-mono)",
  color: "var(--color-dimmer)",
  textAlign: "right",
} as const;

function PlayerRow({ player, side, local }: { player: PlayerLive; side: string; local: boolean }) {
  const testid = local ? "player-row-local" : `player-row-${side}-${player.summoner}`;
  return (
    <div
      data-testid={testid}
      style={{
        display: "flex",
        alignItems: "center",
        gap: 7,
        padding: "4px 8px",
        borderRadius: 10,
        background: local ? "rgba(122,97,255,.16)" : "transparent",
        boxShadow: local ? "inset 0 0 0 1px var(--color-accent)" : "none",
      }}
    >
      <span
        className="mono-n"
        style={{
          fontSize: 9.5,
          color: "#e9e9ed",
          width: 88,
          whiteSpace: "nowrap",
          overflow: "hidden",
          textOverflow: "ellipsis",
        }}
      >
        {player.summoner}
      </span>
      <span
        style={{
          fontSize: 9.5,
          flex: 1,
          minWidth: 0,
          color: "var(--color-dim)",
          whiteSpace: "nowrap",
          overflow: "hidden",
          textOverflow: "ellipsis",
        }}
      >
        {player.champion ?? "—"}
      </span>
      <span className="mono-n" style={{ ...CELL_STYLE, width: 16 }}>
        {player.level}
      </span>
      <span
        className="mono-n"
        data-testid="row-kda"
        style={{ ...CELL_STYLE, width: 46, color: "var(--color-text)" }}
      >
        {player.kills}/{player.deaths}/{player.assists}
      </span>
      <span className="mono-n" data-testid="row-cs" style={{ ...CELL_STYLE, width: 26 }}>
        {player.cs}
      </span>
      <span className="mono-n" data-testid="row-ward" style={{ ...CELL_STYLE, width: 24 }}>
        {player.ward_score.toFixed(1)}
      </span>
    </div>
  );
}

/**
 * Real rosters come from the Live Client Data API (:2999 official spectator
 * data); until it is reachable the rows stay dash placeholders.
 */
export function PlayerList({ snapshot }: { snapshot: InGameSnapshot | undefined }) {
  const active = !!snapshot?.active;
  const order = snapshot?.teams.order ?? [];
  const chaos = snapshot?.teams.chaos ?? [];
  const kills = [...order, ...chaos].reduce((sum, p) => sum + p.kills, 0);
  const turrets = (snapshot?.events ?? []).filter((e) => e.name === "TurretKilled").length;

  return (
    <section
      className="card3b"
      data-testid="player-list"
      style={{
        flex: "none",
        padding: "11px 13px",
        background: "linear-gradient(180deg,var(--color-surface-2),var(--color-surface))",
      }}
    >
      <div style={{ display: "flex", alignItems: "center", gap: 9, marginBottom: 9 }}>
        <Dot color="var(--color-teal)" />
        <span
          style={{
            font: "700 9.5px var(--font-mono)",
            letterSpacing: ".13em",
            color: "var(--color-dim)",
          }}
        >
          PLAYER LIST · LEVEL · K/D/A · CS · WARD SCORE
        </span>
        <span
          className="mono-n"
          data-testid="score-strip"
          style={{ marginLeft: "auto", fontSize: 10, color: active ? "var(--color-text)" : "var(--color-dimmer)" }}
        >
          {active ? `${kills} kills · ${turrets} turrets` : "— kills · — turrets"}
        </span>
      </div>
      {!active && (
        <div style={{ display: "flex", justifyContent: "center", marginBottom: 9 }}>
          <span
            className="pill"
            data-testid="waiting-pill"
            style={{ background: "var(--color-amber-low)", color: "var(--color-amber)" }}
          >
            waiting for :2999
          </span>
        </div>
      )}
      {active ? (
        <div style={{ display: "grid", gridTemplateColumns: "1fr 1px 1fr", gap: 13 }}>
          <div data-testid="team-order" style={{ display: "flex", flexDirection: "column", gap: 3 }}>
            {order.map((p) => (
              <PlayerRow
                key={p.summoner}
                player={p}
                side="order"
                local={snapshot?.local_summoner === p.summoner}
              />
            ))}
          </div>
          <div style={{ background: "linear-gradient(180deg,transparent,var(--color-line),transparent)" }} />
          <div data-testid="team-chaos" style={{ display: "flex", flexDirection: "column", gap: 3 }}>
            {chaos.map((p) => (
              <PlayerRow
                key={p.summoner}
                player={p}
                side="chaos"
                local={snapshot?.local_summoner === p.summoner}
              />
            ))}
          </div>
        </div>
      ) : (
        <div style={{ display: "grid", gridTemplateColumns: "1fr 1px 1fr", gap: 13 }}>
          <SkeletonSide />
          <div style={{ background: "linear-gradient(180deg,transparent,var(--color-line),transparent)" }} />
          <SkeletonSide />
        </div>
      )}
    </section>
  );
}
