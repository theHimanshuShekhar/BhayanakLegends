import type { FindingsPack, LiveEvent, PlayerLive } from "../../api/types";
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
        <span className="mono-n" data-testid="active-player-sub" style={{ fontSize: 10, color: player ? "var(--color-text)" : "var(--color-dimmer)" }}>
          {player
            ? `${player.summoner} · ${player.champion ?? "Unavailable"}`
            : "Unavailable level · Unavailable gold"}
        </span>
      </div>
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
            color: player ? "#e9e9ed" : "var(--color-dimmer)",
          }}
        >
          {player?.champion ? player.champion.replace(/[^a-zA-Z]/g, "").slice(0, 2).toUpperCase() : <span aria-label="Unavailable">Unavailable</span>}
        </div>
        <div style={{ flex: 1 }}>
          <div
            style={{ display: "flex", justifyContent: "space-between", fontSize: 9, color: "var(--color-dim)", marginBottom: 3 }}
          >
            <span>K / D / A</span>
            <span className="mono-n" data-testid="active-kda">
              {player ? `${player.kills} / ${player.deaths} / ${player.assists}` : <span aria-label="Unavailable">Unavailable</span>}
            </span>
          </div>
          <div
            style={{
              height: 8,
              borderRadius: 999,
              background: "var(--color-deep)",
              boxShadow: "inset 0 2px 5px rgba(0,0,0,.8)",
              overflow: "hidden",
            }}
          />
        </div>
      </div>
      <div style={{ marginTop: 10, display: "grid", gridTemplateColumns: "1fr 1fr 1fr", gap: 6 }}>
        {(player
          ? ([
              ["LEVEL", String(player.level)],
              ["CS", String(player.cs)],
              ["WARD", player.ward_score.toFixed(1)],
            ] as const)
          : ([
              ["LEVEL", "Unavailable"],
              ["CS", "Unavailable"],
              ["WARD", "Unavailable"],
            ] as const)
        ).map(([label, value]) => (
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
            <div className="mono-n" style={{ font: "700 14px var(--font-mono)", color: player ? "var(--color-text)" : "var(--color-dimmer)" }}>
              {value}
            </div>
            <div style={{ fontSize: 8, letterSpacing: ".06em", color: "var(--color-dimmer)" }}>{label}</div>
          </div>
        ))}
      </div>
      {!player && (
        <div
          style={{
            marginTop: 9,
            display: "flex",
            gap: 8,
            padding: 9,
            borderRadius: 13,
            background: "var(--color-surface-2)",
            boxShadow: "var(--shadow-z1)",
          }}
        >
          <p style={{ margin: 0, fontSize: 10.5, lineHeight: 1.5, color: "var(--color-dim)" }}>
            Health, level and held gold read from the game state — they land when the :2999 bridge
            connects.
          </p>
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

function TeamBar({ left, label, right }: { left: string; label: string; right: string }) {
  return (
    <div>
      <div style={{ display: "flex", justifyContent: "space-between", fontSize: 9.5, marginBottom: 3 }}>
        <span className="mono-n" style={{ color: "var(--color-dim)" }}>
          {left}
        </span>
        <span style={{ color: "var(--color-dim)", letterSpacing: ".06em" }}>{label}</span>
        <span className="mono-n" style={{ color: "var(--color-dim)" }}>
          {right}
        </span>
      </div>
      <div
        style={{
          height: 6,
          borderRadius: 999,
          overflow: "hidden",
          display: "flex",
          background: "var(--color-deep)",
          boxShadow: "inset 0 2px 4px rgba(0,0,0,.75)",
        }}
      >
        <div style={{ width: "50%", background: "var(--color-surface-3)" }} />
        <div style={{ flex: 1 }} />
      </div>
    </div>
  );
}

export function TeamVsTeamCard({ pack }: { pack: FindingsPack | undefined }) {
  const lanesAhead = pack?.findings.find((f) => f.key === "lanes_ahead");
  return (
    <section
      className="card3"
      style={{ padding: 12, display: "flex", flexDirection: "column", gap: 9 }}
    >
      <CardHead color="var(--color-teal)" label="TEAM VS TEAM" />
      <TeamBar left="Unavailable" label="CS" right="Unavailable" />
      <TeamBar left="Unavailable" label="LEVELS" right="Unavailable" />
      <TeamBar left="Unavailable" label="LANES AHEAD" right="Unavailable" />
      {lanesAhead && (
        <p
          data-testid="lanes-ahead"
          style={{ margin: "auto 0 0", fontSize: 9.5, lineHeight: 1.5, color: "#cfd3e5" }}
        >
          {lanesAhead.statement}
        </p>
      )}
      <p style={{ margin: 0, fontSize: 9.5, color: "var(--color-dimmer)" }}>
        Team totals land with the LCU bridge.
      </p>
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

export function ItemValueCard() {
  return (
    <section
      className="card3"
      data-testid="item-value"
      style={{ padding: 12, flex: 1, minHeight: 0, display: "flex", flexDirection: "column", gap: 7 }}
    >
      <CardHead
        color="var(--color-teal)"
        label="ITEM VALUE BY PLAYER"
        right={
          <span className="mono-n" style={{ fontSize: 9, color: "var(--color-dimmer)" }}>
            priced from inventory
          </span>
        }
      />
      <ul aria-label="Item values" style={{ display: "flex", flexDirection: "column", gap: 7, listStyle: "none", margin: 0, padding: 0 }}>
        {[0, 1, 2].map((i) => (
          <li key={i} style={{ display: "flex", alignItems: "center", gap: 9 }}>
            <div aria-hidden="true" style={{ width: 20, height: 20, flex: "none", borderRadius: 7, background: "var(--color-surface-3)" }} />
            <span aria-label="Unavailable" style={{ width: 54, fontSize: 10, color: "var(--color-dimmer)" }}>Unavailable</span>
            <div
              aria-hidden="true"
              style={{
                flex: 1,
                height: 8,
                borderRadius: 999,
                background: "var(--color-deep)",
                boxShadow: "inset 0 2px 4px rgba(0,0,0,.75)",
              }}
            />
            <span aria-label="Unavailable" className="mono-n" style={{ width: 42, textAlign: "right", fontSize: 10, color: "var(--color-dimmer)" }}>
              Unavailable
            </span>
          </li>
        ))}
      </ul>
      <p style={{ margin: "auto 0 0", fontSize: 9.5, color: "var(--color-dimmer)" }}>
        Item values land with the LCU bridge.
      </p>
    </section>
  );
}

export function DeadNowCard() {
  return (
    <section
      className="card3b"
      data-testid="dead-now"
      style={{ padding: 12, display: "flex", flexDirection: "column", gap: 8 }}
    >
      <CardHead color="var(--color-teal)" label="DEAD RIGHT NOW" />
      <div
        style={{
          display: "flex",
          alignItems: "center",
          justifyContent: "center",
          padding: "10px 8px",
          borderRadius: 13,
          background: "var(--color-surface-2)",
          boxShadow: "var(--shadow-z1)",
          color: "var(--color-dim)",
          fontSize: 10,
        }}
      >
        death tracker lands with the LCU bridge
      </div>
    </section>
  );
}

export function EnemySpellsCard() {
  return (
    <section
      className="card3"
      data-testid="enemy-spells"
      style={{ padding: 12, flex: 1, minHeight: 0, display: "flex", flexDirection: "column", gap: 8 }}
    >
      <CardHead color="var(--color-teal)" label="ENEMY SPELLS" />
      {/* COMPLIANCE (AGENTS.md): enemy ability/ult tracking is out of policy. This panel stays
          a structure placeholder; when the LCU bridge lands it carries the active player's own
          summoner spells only — never enemy timers. */}
      <div
        style={{
          display: "flex",
          alignItems: "center",
          justifyContent: "center",
          padding: "12px 8px",
          borderRadius: 12,
          background: "var(--color-surface-2)",
          boxShadow: "var(--shadow-z1)",
          color: "var(--color-dim)",
          fontSize: 10,
        }}
      >
        ships after LCU bridge
      </div>
      <div style={{ marginTop: "auto", display: "flex", flexDirection: "column", gap: 6 }}>
        <div
          style={{
            display: "flex",
            alignItems: "center",
            gap: 8,
            padding: "8px 9px",
            borderRadius: 12,
            background: "var(--color-accent-low)",
            boxShadow: "var(--shadow-z1)",
          }}
        >
          <div style={{ width: 20, height: 20, flex: "none", borderRadius: 7, background: "var(--color-accent)" }} />
          <div style={{ fontSize: 9.5, lineHeight: 1.35, color: "#e7e5fe" }}>
            Enemy spell timers stay out of policy — active-player summoner spells only, after the
            bridge.
          </div>
        </div>
      </div>
    </section>
  );
}
