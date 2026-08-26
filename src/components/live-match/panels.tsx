import type { InGameSnapshot, LiveEvent, PlayerLive } from "../../api/types";
import { clockLabel, CardHead, Dot } from "./bits";

export function ActivePlayerCard({ player }: { player: PlayerLive | null }) {
  return (
    <section
      className="card3b"
      data-testid="active-player"
      style={{
        padding: 13,
        background: "linear-gradient(165deg,#1f2c31,var(--color-surface-2) 64%)",
        boxShadow:
          "0 4px 0 rgba(0,0,0,.55),0 26px 44px -16px rgba(0,0,0,.9),inset 0 1px 0 rgba(255,255,255,.08)",
      }}
    >
      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: 9 }}>
        <h2 style={{ margin: 0, font: "700 9.5px var(--font-mono)", letterSpacing: ".11em", color: "var(--color-dim)" }}>
          Active player
        </h2>
        {player && (
          <span className="mono-n" data-testid="active-player-sub" style={{ fontSize: 10, color: "var(--color-text)" }}>
            {player.summoner} · {player.champion ?? "Unavailable"}
          </span>
        )}
      </div>
      {player ? (
        <>
          <div style={{ display: "flex", alignItems: "center", gap: 11 }}>
            <div
              style={{
                width: 48,
                height: 48,
                borderRadius: 16,
                background: "var(--color-surface-3)",
                display: "grid",
                placeItems: "center",
                font: "700 14px var(--font-mono)",
                color: "#e9e9ed",
              }}
            >
              {player.champion ? player.champion.replace(/[^a-zA-Z]/g, "").slice(0, 2).toUpperCase() : (
                <>
                  <span aria-hidden="true">—</span>
                  <span className="sr-only">Unavailable</span>
                </>
              )}
            </div>
            <div style={{ flex: 1 }}>
              <div
                style={{ display: "flex", justifyContent: "space-between", fontSize: 9, color: "var(--color-dim)" }}
              >
                <span>K / D / A</span>
                <span
                  className="mono-n"
                  data-testid="active-kda"
                  aria-label={`Kills ${player.kills}; deaths (cumulative) ${player.deaths}; assists ${player.assists}`}
                >
                  {`${player.kills} / ${player.deaths} / ${player.assists}`}
                </span>
              </div>
            </div>
          </div>
          <div style={{ marginTop: 10, display: "grid", gridTemplateColumns: "1fr 1fr 1fr", gap: 6 }}>
            {([
              ["LEVEL", String(player.level)],
              ["CS", String(player.cs)],
              ["WARD", player.ward_score.toFixed(1)],
            ] as const).map(([label, value]) => (
              <div
                key={label}
                data-testid={`active-stat-${label.toLowerCase()}`}
                style={{
                  padding: "7px 8px",
                  borderRadius: 11,
                  background: "rgba(10,11,22,.5)",
                  boxShadow: "inset 0 2px 5px rgba(0,0,0,.55)",
                }}
              >
                <div className="mono-n" style={{ font: "700 14px var(--font-mono)", color: "var(--color-text)" }}>
                  {value}
                </div>
                <div style={{ fontSize: 8, letterSpacing: ".06em", color: "var(--color-dimmer)" }}>{label}</div>
              </div>
            ))}
          </div>
        </>
      ) : (
        <div
          data-testid="active-player-unavailable"
          style={{
            padding: "16px 9px",
            borderRadius: 13,
            background: "var(--color-surface-2)",
            boxShadow: "var(--shadow-z1)",
            color: "var(--color-dim)",
            fontSize: 10.5,
            textAlign: "center",
          }}
        >
          Local player unavailable
        </div>
      )}
    </section>
  );
}

export function CheatSheetCard() {
  return (
    <section className="card3" aria-labelledby="cheat-sheet-heading" style={{ padding: "10px 12px", display: "flex", alignItems: "center", gap: 9 }}>
      <Dot color="var(--color-info)" />
      <h2 id="cheat-sheet-heading" style={{ margin: 0, font: "700 9.5px var(--font-mono)", letterSpacing: ".11em", color: "var(--color-dim)" }}>
        ROLE CHEAT-SHEET
      </h2>
      <div style={{ fontSize: 10, lineHeight: 1.4, color: "#cfd3e5" }}>
        <b style={{ color: "#e9e9ed" }}>Role cheat-sheet:</b> the per-role lever list (lane gold,
        plates, show timing) is pulled from the Findings Pack once the live bridge names your role.
      </div>
    </section>
  );
}

type TeamKey = "order" | "chaos";

type TeamTotals = {
  cs: number;
  level: number;
  kills: number;
  deaths: number;
};

function teamTotals(players: PlayerLive[]): TeamTotals {
  return players.reduce(
    (totals, player) => ({
      cs: totals.cs + player.cs,
      level: totals.level + player.level,
      kills: totals.kills + player.kills,
      deaths: totals.deaths + player.deaths,
    }),
    { cs: 0, level: 0, kills: 0, deaths: 0 },
  );
}

const TEAM_TOTAL_FIELDS = [
  ["CS", "cs"],
  ["Levels", "level"],
  ["Kills", "kills"],
  ["Deaths", "deaths"],
] as const;

export function TeamVsTeamCard({ snapshot }: { snapshot: InGameSnapshot | undefined }) {
  const active = !!snapshot?.active;
  const teams: { key: TeamKey; label: string; players: PlayerLive[] }[] = [
    { key: "order", label: "Order", players: snapshot?.teams.order ?? [] },
    { key: "chaos", label: "Chaos", players: snapshot?.teams.chaos ?? [] },
  ];

  return (
    <section
      className="card3"
      data-testid="team-totals"
      style={{ padding: 12, display: "flex", flexDirection: "column", gap: 9 }}
    >
      <CardHead color={active ? "var(--color-teal)" : "var(--color-dimmer)"} label="TEAM VS TEAM" />
      {active ? (
        <div className="live-table-scroll" aria-label="Team totals table">
          <table aria-label="Team totals" style={{ width: "100%", borderCollapse: "collapse", tableLayout: "fixed" }}>
            <caption style={{ position: "absolute", width: 1, height: 1, padding: 0, margin: -1, overflow: "hidden", clip: "rect(0, 0, 0, 0)", whiteSpace: "nowrap", border: 0 }}>
              Team totals
            </caption>
            <thead>
              <tr>
                <th scope="col" style={{ padding: "0 6px 5px", textAlign: "left", fontSize: 8, color: "var(--color-dimmer)" }}>Team</th>
                {TEAM_TOTAL_FIELDS.map(([label]) => (
                  <th key={label} scope="col" style={{ padding: "0 6px 5px", textAlign: "right", fontSize: 8, color: "var(--color-dimmer)" }}>{label}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {teams.map(({ key, label, players }) => {
                const totals = teamTotals(players);
                return (
                  <tr key={key} data-testid={`team-total-row-${key}`}>
                    <th scope="row" style={{ padding: "5px 6px", textAlign: "left", font: "700 9px var(--font-mono)", color: "var(--color-dim)" }}>{label}</th>
                    {TEAM_TOTAL_FIELDS.map(([field, property]) => (
                      <td key={field} data-testid={`team-total-${key}-${property}`} className="mono-n" style={{ padding: "5px 6px", textAlign: "right", fontSize: 10, color: "var(--color-text)" }}>
                        {totals[property]}
                      </td>
                    ))}
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      ) : (
        <p data-testid="team-totals-unavailable" style={{ margin: 0, color: "var(--color-dimmer)", fontSize: 10 }}>No snapshot</p>
      )}
    </section>
  );
}

export function EventFeedCard({ events }: { events: LiveEvent[] }) {
  return (
    <section
      className="card3"
      data-testid="event-feed"
      style={{ padding: 12, display: "flex", flexDirection: "column", gap: 8 }}
    >
      <CardHead
        color="var(--color-teal)"
        label="EVENT FEED"
        right={
          <span className="mono-n" style={{ fontSize: 9, color: "var(--color-dimmer)" }}>
            {events.length} events
          </span>
        }
      />
      {events.length ? (
        <ul
          aria-label="Live events"
          data-testid="event-feed-rows"
          style={{ display: "flex", flexDirection: "column", gap: 4, maxHeight: 168, overflowY: "auto", listStyle: "none", margin: 0, padding: 0 }}
        >
          {events.map((event, i) => (
            <li
              key={`${event.name}-${event.t_s}-${i}`}
              data-testid={`event-row-${i}`}
              style={{
                display: "flex",
                alignItems: "center",
                gap: 8,
                padding: "5px 8px",
                borderRadius: 9,
                background: "rgba(10,11,22,.45)",
              }}
            >
              <span className="mono-n" style={{ fontSize: 9, color: "var(--color-dimmer)", flex: "none" }}>
                {clockLabel(event.t_s)}
              </span>
              <span
                className="mono-n"
                data-testid={`event-name-${i}`}
                style={{ fontSize: 9.5, color: "var(--color-text)" }}
              >
                {event.name}
                {event.detail ? ` · ${event.detail}` : ""}
              </span>
              {(event.actor || event.victim) && (
                <span
                  className="mono-n"
                  style={{
                    fontSize: 9,
                    marginLeft: "auto",
                    color: "var(--color-dim)",
                    whiteSpace: "nowrap",
                    overflow: "hidden",
                    textOverflow: "ellipsis",
                  }}
                >
                  {event.actor ?? "?"}
                  {event.victim ? ` → ${event.victim}` : ""}
                </span>
              )}
            </li>
          ))}
        </ul>
      ) : (
        <div
          style={{
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
            padding: "14px 8px",
            borderRadius: 11,
            border: "1px dashed var(--color-line)",
            color: "var(--color-dim)",
            fontSize: 10,
          }}
        >
          event feed lands with the LCU bridge
        </div>
      )}
    </section>
  );
}

export function ItemsByPlayerCard({ snapshot }: { snapshot: InGameSnapshot | undefined }) {
  const active = !!snapshot?.active;
  const teams: { key: TeamKey; label: string; players: PlayerLive[] }[] = [
    { key: "order", label: "Order", players: snapshot?.teams.order ?? [] },
    { key: "chaos", label: "Chaos", players: snapshot?.teams.chaos ?? [] },
  ];

  return (
    <section
      className="card3"
      data-testid="items-by-player"
      style={{ padding: 12, flex: 1, minHeight: 0, display: "flex", flexDirection: "column", gap: 7 }}
    >
      <CardHead color={active ? "var(--color-teal)" : "var(--color-dimmer)"} label="ITEMS BY PLAYER" />
      {active ? (
        <div style={{ display: "flex", flexDirection: "column", gap: 9 }}>
          {teams.map(({ key, label, players }) => (
            <section key={key} aria-labelledby={`items-${key}-heading`}>
              <h3 id={`items-${key}-heading`} style={{ margin: "2px 0 5px", font: "700 8.5px var(--font-mono)", letterSpacing: ".1em", color: "var(--color-dim)" }}>{label}</h3>
              <ul aria-label={`${label} items by player`} style={{ display: "flex", flexDirection: "column", gap: 5, listStyle: "none", margin: 0, padding: 0 }}>
                {players.map((player) => (
                  <li key={`${key}-${player.summoner}`} data-testid={`items-player-${key}-${player.summoner}`} style={{ display: "flex", alignItems: "baseline", gap: 8, fontSize: 9.5 }}>
                    <span style={{ minWidth: 110, color: "var(--color-dim)", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{player.summoner}</span>
                    {player.items.length ? (
                      <ul aria-label={`${player.summoner} items`} style={{ display: "flex", flexWrap: "wrap", gap: 5, listStyle: "none", margin: 0, padding: 0 }}>
                        {player.items.map((item, index) => (
                          <li key={`${item.id}-${index}`} data-testid={`item-${key}-${player.summoner}-${index}`} style={{ color: "var(--color-text)" }}>
                            <span>Item {item.id}</span>{" "}
                            <span className="mono-n" style={{ color: "var(--color-dim)" }}>count {item.count}</span>
                          </li>
                        ))}
                      </ul>
                    ) : (
                      <span style={{ color: "var(--color-dimmer)" }}>No items reported</span>
                    )}
                  </li>
                ))}
              </ul>
            </section>
          ))}
        </div>
      ) : (
        <p data-testid="items-unavailable" style={{ margin: 0, color: "var(--color-dimmer)", fontSize: 10 }}>No snapshot</p>
      )}
    </section>
  );
}
