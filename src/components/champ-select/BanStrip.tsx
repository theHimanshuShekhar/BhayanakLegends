import type {
  ChampSelectAllyCell,
  ChampSelectBan,
  ChampSelectEnemyCell,
  ChampSelectSnapshot,
} from "../../api/types";
import { initials } from "./shared";

const ALLY_TILE_BG = "linear-gradient(150deg,#454a66,#22263a)";
const ENEMY_TILE_BG = "linear-gradient(150deg,#5a3644,#2b1a22)";
const ENEMY_PICKED_TILE_BG = "linear-gradient(150deg,#8a3a50,#3d1626)";

export function championLabel(champion: string | null | undefined, championId: number): string {
  if (!championId) return "choosing…";
  return champion ?? `Champion ${championId}`;
}

export const STATE_CAPTION: Record<string, string> = {
  picked: "picked",
  intent: "intent",
  hover: "hover",
  none: "—",
};

function SlashTile({ plain = false }: { plain?: boolean }) {
  return (
    <div
      style={{
        width: 26,
        height: 26,
        borderRadius: 9,
        background: plain ? "#2b2f45" : "#22263a",
        boxShadow: "inset 0 2px 5px rgba(0,0,0,.6)",
        position: "relative",
        flex: "none",
      }}
    >
      {!plain && (
        <div
          style={{
            position: "absolute",
            inset: 0,
            borderRadius: 9,
            background:
              "linear-gradient(45deg,transparent 46%,var(--color-danger) 46%,var(--color-danger) 54%,transparent 54%)",
            opacity: 0.45,
          }}
        />
      )}
    </div>
  );
}

/**
 * Real ban tile: 2-letter mono initials on a gradient; unknown champion ids
 * fall back to a "?" tile titled "Champion {id}" (full text lives in the
 * bans caption line below the strip).
 */
function BanTile({
  ban,
  side,
}: {
  ban: ChampSelectBan | undefined;
  side: "ally" | "enemy";
}) {
  if (!ban || !ban.champion_id) return <SlashTile plain={side === "enemy"} />;
  const label = ban.name ? initials(ban.name) : "?";
  return (
    <div
      title={ban.name ?? `Champion ${ban.champion_id}`}
      style={{
        width: 26,
        height: 26,
        borderRadius: 9,
        flex: "none",
        background:
          side === "enemy" && !ban.name ? ENEMY_PICKED_TILE_BG : side === "enemy" ? ENEMY_TILE_BG : ALLY_TILE_BG,
        display: "grid",
        placeItems: "center",
        font: "700 10px var(--font-mono)",
        color: "#e9e9ed",
        boxShadow: "inset 0 2px 5px rgba(0,0,0,.55)",
      }}
    >
      {label}
    </div>
  );
}

function Divider() {
  return (
    <div
      style={{ flex: 1, height: 1, background: "linear-gradient(90deg,transparent,var(--color-line),transparent)" }}
    />
  );
}

function RosterTile({
  championName,
  enemyPicked,
}: {
  championName: string | null;
  enemyPicked: boolean;
}) {
  const known = championName != null && championName !== "";
  const label = known && championName !== "choosing…" ? initials(championName) : "?";
  return (
    <div
      style={{
        width: 30,
        height: 30,
        flex: "none",
        borderRadius: 10,
        background: enemyPicked ? ENEMY_PICKED_TILE_BG : known ? ALLY_TILE_BG : ENEMY_TILE_BG,
        display: "grid",
        placeItems: "center",
        font: "700 12px var(--font-mono)",
        color: "#b2b6ca",
      }}
    >
      {label}
    </div>
  );
}

function AllySlot({ cell }: { cell: ChampSelectAllyCell }) {
  const champion = championLabel(cell.champion, cell.champion_id);
  return (
    <div
      data-testid={`cs-ally-cell-${cell.cell_id}`}
      style={{
        flex: 1,
        minWidth: 0,
        display: "flex",
        alignItems: "center",
        gap: 8,
        padding: "6px 10px 6px 6px",
        borderRadius: 14,
        background: "var(--color-surface-3)",
        boxShadow: cell.is_local
          ? "inset 0 0 0 1px var(--color-accent),var(--shadow-z1)"
          : "var(--shadow-z1)",
      }}
    >
      <RosterTile championName={champion} enemyPicked={false} />
      <div style={{ minWidth: 0 }}>
        <div style={{ font: "600 11px var(--font-mono)", whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis" }}>
          {champion}
        </div>
        <div style={{ fontSize: 9, color: "var(--color-dimmer)" }}>{STATE_CAPTION[cell.state] ?? cell.state}</div>
      </div>
      {cell.is_local && (
        <span
          className="pill"
          style={{ marginLeft: "auto", flex: "none", background: "var(--color-accent)", color: "#0e1020", fontSize: 8 }}
        >
          YOU
        </span>
      )}
    </div>
  );
}

// COMPLIANCE (Riot policy): ranked enemy summoner names must never render in
// champ select. The sidecar strips theirTeam names at the service layer, so
// these slots carry champion-level intel only — there is no name to leak.
function EnemySlot({ cell }: { cell: ChampSelectEnemyCell }) {
  const picked = cell.state === "picked";
  const name = championLabel(cell.champion, cell.champion_id);
  return (
    <div
      data-testid={`cs-enemy-cell-${cell.cell_id}`}
      style={{
        flex: 1,
        minWidth: 0,
        display: "flex",
        alignItems: "center",
        gap: 8,
        padding: "6px 10px 6px 6px",
        borderRadius: 14,
        background: "var(--color-surface-3)",
        boxShadow: picked ? "inset 0 0 0 1px var(--color-danger),var(--shadow-z1)" : "var(--shadow-z1)",
      }}
    >
      <RosterTile championName={name} enemyPicked={picked} />
      <div style={{ minWidth: 0 }}>
        <div style={{ font: "600 11px var(--font-mono)", whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis" }}>
          {name}
        </div>
        <div style={{ fontSize: 9, color: "var(--color-dimmer)" }}>{STATE_CAPTION[cell.state] ?? cell.state}</div>
      </div>
    </div>
  );
}

function EmptyAllySlot() {
  return (
    <div
      style={{
        flex: 1,
        display: "flex",
        alignItems: "center",
        gap: 8,
        padding: "6px 10px 6px 6px",
        borderRadius: 14,
        background: "var(--color-surface-3)",
        boxShadow: "var(--shadow-z1)",
      }}
    >
      <div
        style={{
          width: 30,
          height: 30,
          flex: "none",
          borderRadius: 10,
          background: ALLY_TILE_BG,
          display: "grid",
          placeItems: "center",
          font: "700 12px var(--font-mono)",
          color: "#6a6f88",
        }}
      >
        ?
      </div>
      <div style={{ fontSize: 9, color: "var(--color-dimmer)" }}>joining…</div>
    </div>
  );
}

function EmptyEnemySlot() {
  return (
    <div
      style={{
        flex: 1,
        display: "flex",
        alignItems: "center",
        gap: 8,
        padding: "6px 10px 6px 6px",
        borderRadius: 14,
        background: "var(--color-surface-3)",
        boxShadow: "var(--shadow-z1)",
      }}
    >
      <div
        style={{
          width: 30,
          height: 30,
          flex: "none",
          borderRadius: 10,
          background: ENEMY_TILE_BG,
          display: "grid",
          placeItems: "center",
          font: "700 12px var(--font-mono)",
          color: "#6a6f88",
        }}
      >
        ?
      </div>
      <div style={{ fontSize: 9, color: "var(--color-dimmer)" }}>not revealed</div>
    </div>
  );
}

function IdleBanner({ lastError }: { lastError: string | null }) {
  return (
    <div
      data-testid="cs-idle-banner"
      style={{
        flex: "none",
        borderRadius: 18,
        padding: "16px 14px",
        background: "linear-gradient(180deg,var(--color-surface-2),var(--color-surface))",
        boxShadow: "var(--shadow-z2)",
      }}
    >
      <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
        <span
          style={{ width: 6, height: 6, borderRadius: 999, background: "var(--color-amber)", flex: "none" }}
        />
        <span style={{ fontSize: 10, lineHeight: 1.4, color: "var(--color-dim)" }}>
          Ranked draft hides enemy summoner names — the app shows champion-level intel only.
        </span>
        <div
          className="pill"
          style={{
            marginLeft: "auto",
            background: "var(--color-surface-3)",
            color: "var(--color-dim)",
            boxShadow: "var(--shadow-z1)",
          }}
        >
          waiting for client
        </div>
      </div>
      {lastError && (
        <div
          data-testid="detection-status"
          style={{
            marginTop: 6,
            font: "600 9px var(--font-mono)",
            letterSpacing: ".06em",
            color: "var(--color-amber)",
          }}
        >
          client detection: {lastError}
        </div>
      )}
    </div>
  );
}

function banCaption(bans: ChampSelectBan[]): string {
  if (!bans.length) return "none yet";
  return bans.map((b) => b.name ?? `Champion ${b.champion_id}`).join(", ");
}

export function BanStrip({
  snapshot,
  timerLabel,
  timerUrgent = false,
  lastError,
}: {
  snapshot: ChampSelectSnapshot | undefined;
  timerLabel: string;
  timerUrgent?: boolean;
  lastError: string | null;
}) {
  if (!snapshot?.active) return <IdleBanner lastError={lastError} />;

  const allyBans = [...(snapshot.bans_ally ?? [])].slice(0, 5);
  const enemyBans = [...(snapshot.bans_enemy ?? [])].slice(0, 5);
  const allyCells = (snapshot.ally ?? []).slice(0, 5);
  const enemyCells = (snapshot.enemy ?? []).slice(0, 5);

  return (
    <div
      data-testid="cs-ban-strip"
      style={{
        flex: "none",
        borderRadius: 18,
        padding: "11px 14px 12px",
        background: "linear-gradient(180deg,var(--color-surface-2),var(--color-surface))",
        boxShadow: "var(--shadow-z2)",
      }}
    >
      <div style={{ display: "flex", alignItems: "center", gap: 9, marginBottom: 10 }}>
        <span className="kicker">BANS</span>
        <div style={{ display: "flex", gap: 5 }}>
          {Array.from({ length: 5 }, (_, i) => (
            <BanTile key={`ally-ban-${i}`} ban={allyBans[i]} side="ally" />
          ))}
        </div>
        <Divider />
        <div
          className={`pill mono-n${timerUrgent ? " bl-pulse" : ""}`}
          data-testid="cs-timer-pill"
          style={
            timerUrgent
              ? { background: "var(--color-amber)", color: "#0e1020", whiteSpace: "nowrap" }
              : { background: "var(--color-accent)", color: "#0e1020", whiteSpace: "nowrap" }
          }
        >
          {snapshot.phase ?? "champ select"} · {timerLabel}
        </div>
        <Divider />
        <div style={{ display: "flex", gap: 5 }}>
          {Array.from({ length: 5 }, (_, i) => (
            <BanTile key={`enemy-ban-${i}`} ban={enemyBans[i]} side="enemy" />
          ))}
        </div>
        <span className="kicker">BANS</span>
      </div>

      <div style={{ display: "grid", gridTemplateColumns: "1fr 1px 1fr", gap: 14, alignItems: "stretch" }}>
        <div style={{ display: "flex", gap: 7 }} data-testid="cs-ally-row">
          {allyCells.map((cell) => (
            <AllySlot key={cell.cell_id} cell={cell} />
          ))}
          {Array.from({ length: Math.max(0, 5 - allyCells.length) }, (_, i) => (
            <EmptyAllySlot key={`ally-pad-${i}`} />
          ))}
        </div>
        <div style={{ background: "linear-gradient(180deg,transparent,var(--color-line),transparent)" }} />
        <div style={{ display: "flex", gap: 7 }} data-testid="cs-enemy-row">
          {enemyCells.map((cell) => (
            <EnemySlot key={cell.cell_id} cell={cell} />
          ))}
          {Array.from({ length: Math.max(0, 5 - enemyCells.length) }, (_, i) => (
            <EmptyEnemySlot key={`enemy-pad-${i}`} />
          ))}
        </div>
      </div>

      <div
        style={{
          marginTop: 9,
          display: "flex",
          alignItems: "center",
          gap: 8,
          padding: "7px 11px",
          borderRadius: 999,
          background: "rgba(10,11,22,.5)",
          boxShadow: "inset 0 2px 5px rgba(0,0,0,.5)",
        }}
      >
        <span className="kicker" style={{ flex: "none" }}>
          BANS
        </span>
        <span
          data-testid="cs-bans-caption"
          style={{ fontSize: 10, lineHeight: 1.4, color: "var(--color-dim)", minWidth: 0 }}
        >
          ally: {banCaption(snapshot.bans_ally)} — enemy: {banCaption(snapshot.bans_enemy)}
        </span>
        <span
          style={{
            marginLeft: "auto",
            flex: "none",
            fontSize: 10,
            lineHeight: 1.4,
            color: "var(--color-dim)",
          }}
        >
          Ranked draft hides enemy summoner names until the loading screen — everything on the right is
          champion-level only.
        </span>
      </div>
    </div>
  );
}
