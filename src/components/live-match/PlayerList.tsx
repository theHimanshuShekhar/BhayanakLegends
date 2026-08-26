import type { InGameSnapshot, PlayerLive } from "../../api/types";
import { Dot } from "./bits";

const SKELETON_ROWS = 3;

function SkeletonShape({ width = "100%" }: { width?: string }) {
  return (
    <span
      aria-hidden="true"
      className="live-skeleton"
      style={{ display: "block", width, height: 12, borderRadius: 6, background: "var(--color-surface-3)" }}
    />
  );
}

function SkeletonTableBody() {
  return (
    <tbody aria-hidden="true">
      <tr>
        <td colSpan={7} style={{ padding: 8 }}>
          <div style={{ display: "grid", gap: 7 }}>
            {Array.from({ length: SKELETON_ROWS * 2 }, (_, row) => (
              <div key={row} style={{ display: "grid", gridTemplateColumns: "70px 1fr 1fr 34px 60px 34px 44px", gap: 8 }}>
                {Array.from({ length: 7 }, (_, cell) => <SkeletonShape key={cell} width={cell === 1 ? "80%" : "100%"} />)}
              </div>
            ))}
          </div>
        </td>
      </tr>
    </tbody>
  );
}

const CELL_STYLE = {
  font: "700 9px var(--font-mono)",
  color: "var(--color-dimmer)",
  textAlign: "right",
} as const;

function Scalar({ value }: { value: string | number }) {
  return <span className="mono-n" style={CELL_STYLE}>{value}</span>;
}

function PlayerRow({ player, side, local }: { player: PlayerLive; side: string; local: boolean }) {
  const testid = local ? "player-row-local" : `player-row-${side}-${player.summoner}`;
  return (
    <tr data-testid={testid} style={{ background: local ? "rgba(122,97,255,.16)" : undefined }}>
      <th scope="row" style={{ padding: "4px 8px", font: "600 9px var(--font-mono)", color: "var(--color-dim)", textAlign: "left" }}>
        {side === "order" ? "Ally" : "Enemy"}
      </th>
      <td style={{ padding: "4px 8px", font: "600 9.5px var(--font-mono)", color: "#e9e9ed", maxWidth: 140, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
        {player.summoner}
      </td>
      <td style={{ padding: "4px 8px", fontSize: 9.5, color: "var(--color-dim)", maxWidth: 140, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
        {player.champion ?? <span aria-label="Unavailable">Unavailable</span>}
      </td>
      <td style={{ padding: "4px 8px", textAlign: "right" }}><Scalar value={player.level} /></td>
      <td data-testid="row-kda" style={{ padding: "4px 8px", textAlign: "right" }}><Scalar value={`${player.kills}/${player.deaths}/${player.assists}`} /></td>
      <td data-testid="row-cs" style={{ padding: "4px 8px", textAlign: "right" }}><Scalar value={player.cs} /></td>
      <td data-testid="row-ward" style={{ padding: "4px 8px", textAlign: "right" }}><Scalar value={player.ward_score.toFixed(1)} /></td>
    </tr>
  );
}

/**
 * Real rosters come from the Live Client Data API (:2999 official spectator
 * data); until it is reachable the table stays a visual skeleton.
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
      aria-labelledby="player-roster-heading"
      aria-busy={!active}
      style={{ flex: "none", padding: "11px 13px", background: "linear-gradient(180deg,var(--color-surface-2),var(--color-surface))" }}
    >
      <div style={{ display: "flex", alignItems: "center", gap: 9, marginBottom: 9 }}>
        <Dot color="var(--color-teal)" />
        <h2 id="player-roster-heading" style={{ margin: 0, font: "700 9.5px var(--font-mono)", letterSpacing: ".13em", color: "var(--color-dim)" }}>
          PLAYER ROSTER
        </h2>
        <span className="mono-n" data-testid="score-strip" style={{ marginLeft: "auto", fontSize: 10, color: active ? "var(--color-text)" : "var(--color-dimmer)" }}>
          {active ? `${kills} kills · ${turrets} turrets` : "Unavailable kills · Unavailable turrets"}
        </span>
      </div>
      {!active && (
        <p
          role="status"
          aria-live="polite"
          data-testid="waiting-pill"
          style={{ margin: "0 0 9px", textAlign: "center", fontSize: 10, color: "var(--color-amber)" }}
        >
          waiting for :2999
        </p>
      )}
      <div className="live-table-scroll" aria-label="Player roster table">
        <table aria-label="Player roster" style={{ width: "100%", borderCollapse: "collapse", tableLayout: "fixed" }}>
          <caption style={{ position: "absolute", width: 1, height: 1, padding: 0, margin: -1, overflow: "hidden", clip: "rect(0, 0, 0, 0)", whiteSpace: "nowrap", border: 0 }}>Player roster</caption>
          <thead>
            <tr>
              <th scope="col" style={{ padding: "0 8px 5px", fontSize: 8, color: "var(--color-dimmer)", textAlign: "left" }}>Team</th>
              <th scope="col" style={{ padding: "0 8px 5px", fontSize: 8, color: "var(--color-dimmer)", textAlign: "left" }}>Player</th>
              <th scope="col" style={{ padding: "0 8px 5px", fontSize: 8, color: "var(--color-dimmer)", textAlign: "left" }}>Champion</th>
              <th scope="col" style={{ padding: "0 8px 5px", fontSize: 8, color: "var(--color-dimmer)", textAlign: "right" }}>Level</th>
              <th scope="col" style={{ padding: "0 8px 5px", fontSize: 8, color: "var(--color-dimmer)", textAlign: "right" }}>K/D/A</th>
              <th scope="col" style={{ padding: "0 8px 5px", fontSize: 8, color: "var(--color-dimmer)", textAlign: "right" }}>CS</th>
              <th scope="col" style={{ padding: "0 8px 5px", fontSize: 8, color: "var(--color-dimmer)", textAlign: "right" }}>Ward</th>
            </tr>
          </thead>
          {active ? (
            <>
              <tbody data-testid="team-order">
                {order.map((p) => (
                  <PlayerRow key={`order-${p.summoner}`} player={p} side="order" local={snapshot?.local_summoner === p.summoner} />
                ))}
              </tbody>
              <tbody data-testid="team-chaos">
                {chaos.map((p) => (
                  <PlayerRow key={`chaos-${p.summoner}`} player={p} side="chaos" local={snapshot?.local_summoner === p.summoner} />
                ))}
              </tbody>
            </>
          ) : <SkeletonTableBody />}
        </table>
      </div>
    </section>
  );
}
