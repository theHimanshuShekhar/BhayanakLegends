# Bhayanak Legends v1 — Interface Contract

Single source of truth for frontend↔backend↔pack interfaces. Change here, not ad hoc.

## Process model

Tauri shell spawns the Python sidecar (`bhayanak_legends.sidecar`) with env `BHAYANAK_PORT`, `BHAYANAK_TOKEN`. All HTTP requires header `X-BL-Token: <token>`. The only exception: `/events` also accepts `?token=` because EventSource cannot set headers.

Frontend obtains `{port, token}` via Tauri command `sidecar_info`. In web-only dev (`pnpm dev` without Tauri), defaults: port from `VITE_BL_PORT` (default 23110), token from `VITE_BL_TOKEN` (default "dev").

## REST API (v1)

Base URL: `http://127.0.0.1:{port}`

| Method | Path | Response | Notes |
|---|---|---|---|
| GET | /health | `Health` | liveness + versions |
| GET | /pack | `FindingsPack` | full pack JSON (validated) |
| GET | /settings | `Settings` | |
| PUT | /settings | `Settings` | body: partial `SettingsPatch` |
| POST | /sync/start | `SyncStatus` | kicks era-first backfill (no-op if running) |
| POST | /sync/cancel | `SyncStatus` | |
| GET | /sync/status | `SyncStatus` | |
| GET | /progress/aggregates | `PatchAggregate[]` | true Personal History patch aggregates; query: `patch?`, `role?`, `champion?` |
| GET | /progress/trajectories | `TrajectoryPoint[]` | per-match rolling line; query: `patch?`, `role?`, `champion?` |
| GET | /postgame/latest | `PostGameDigest \| null` | null = none yet |
| GET | /benchmarks | `RoleBenchmark[]` | population medians + personal values |
| GET | /live/status | `LiveStatus` | coarse LCU + in-game health |
| GET | /live/session | `ChampSelectSnapshot` | rich champ-select state; idle → `{active:false,...}` |
| GET | /live/ingame | `InGameSnapshot` | rich in-game state; idle → `{active:false,...}` |
| GET | /events | SSE stream | see Events |

### Types (mirrored in `src/api/types.ts`; python side in `bhayanak_legends.models`)

```ts
type FindingTier = "actionable" | "diagnostic" | "a-lite";

interface Health { status: "ok"; app_version: string; pack_version: string; }
interface Settings {
  riot_id: string | null;        // "GameName#TAG"
  region_route: string;          // "sea" | "americas" | "europe" | "asia"
  has_key: boolean;              // never returns the key itself
  auto_sync: boolean;
}
interface SettingsPatch { riot_id?: string|null; region_route?: string; riot_key?: string|null; auto_sync?: boolean; }

interface SyncStatus {
  state: "idle"|"running"|"cancelled"|"error";
  mode: "era_first"|"import";
  total_queued: number; downloaded: number; skipped: number; failed: number;
  current_match_id: string | null;
  started_at: string | null;      // ISO
}

interface HistorySummary {
  matches: number;
  patches: string[];              // ascending
  by_role: RoleRow[];
  win_rate: number;               // 0..1
}
interface RoleRow { role: string; games: number; wins: number; }

interface TrajectoryPoint {
  patch: string; role: string; champion: string | null;
  played_at: string;                       // match timestamp, ISO
  index: number;                           // chronological index in this response
  rolling_wr: number;                      // 0..1 over the rolling window
}
interface PatchAggregate {
  patch: string;
  games: number; wins: number; win_rate: number; // true counts from Personal History
}

interface PostGameDigest {
  match_id: string;
  played_at: string;              // ISO
  champion: string; role: string; win: boolean; duration_s: number;
  checkpoints: { gold_diff_10: number|null; gold_diff_15: number|null; gold_diff_20: number|null };
  habits: HabitOutcome[];         // four surviving habits where computable
  headline: string;               // one-line takeaway, tier-respecting phrasing
}
interface HabitOutcome { key: string; label: string; value: string; verdict: "good"|"bad"|"neutral"|"n/a"; }

interface RoleBenchmark {
  role: string;
  personal: { cs10: number|null; level10: number|null; gold10: number|null; };
  population: { cs10_median: number; level10_median: number; gold10_median: number; sample: number };
}

interface LiveStatus {
  champ_select: { active: boolean; phase: string|null };   // LCU detected session
  ingame: { active: boolean; game_id: number|null; mode: string|null; clock_s: number };
  last_error: string | null;
}

// Rich LCU-bridge snapshots (GET /live/session + SSE "champselect.state").
// COMPLIANCE: enemy summoner names are stripped at the service layer —
// ChampSelectSnapshot.enemy[].name is always null.
interface ChampSelectBan { champion_id: number; name: string|null }   // name null → UI shows "Champion {id}"
interface ChampSelectAllyCell {
  cell_id: number;
  champion_id: number;
  champion: string|null;         // Data Dragon display name; null → UI shows "Champion {id}"
  name: string|null;             // teammate summoner name when the LCU exposes it
  is_local: boolean;
  state: "intent"|"picked"|"hover"|"none";
}
interface ChampSelectEnemyCell {
  cell_id: number;
  champion_id: number;
  champion: string|null;
  name: string|null;             // always null — compliance
  state: "intent"|"picked"|"hover"|"none";
}
interface ChampSelectSnapshot {
  active: boolean;
  phase: string|null;            // LCU gameflow phase, e.g. "ChampSelect"
  timer_sec: number|null;        // adjustedTimeLeftInSec; client ticks down between frames
  bans_ally: ChampSelectBan[];
  bans_enemy: ChampSelectBan[];
  ally: ChampSelectAllyCell[];
  enemy: ChampSelectEnemyCell[];
}

// Rich in-game snapshots (GET /live/ingame + SSE "live.state"); from the Live
// Client Data API on :2999. Summoner names here are official spectator data.
interface ItemLive { id: number; count: number }
interface PlayerLive {
  summoner: string;
  champion: string|null;
  level: number;
  kills: number; deaths: number; assists: number;
  cs: number;                    // scores.creepScore
  ward_score: number;            // scores.wardScore
  items: ItemLive[];
}
interface LiveEvent {
  name: string;                  // GameStart|MinionsSpawning|FirstBrick|DragonKill|HeraldKill|BaronKill|ChampionKill|TurretKilled|InhibKilled|GameEnd
  t_s: number;                   // EventTime
  actor: string|null; victim: string|null;
  detail: string|null;           // DragonType on DragonKill
}
interface InGameSnapshot {
  active: boolean;
  clock_s: number;               // gameData.gameTime; client ticks between frames
  mode: string|null;
  local_summoner: string|null;
  local_champion: string|null;
  teams: { order: PlayerLive[]; chaos: PlayerLive[] };
  events: LiveEvent[];           // last 40, oldest first
}
```

### SSE events (envelope `{type, ts, data}`)

| type | data |
|---|---|
| `sync.progress` | `SyncStatus` |
| `sync.done` | `SyncStatus` (terminal) |
| `champselect.state` | `ChampSelectSnapshot` |
| `live.state` | `InGameSnapshot` |
| `live.status` | `LiveStatus` (coarse health) |
| `pack.updated` | `{schema_version}` |
| `hello` | `{app_version, pack_version}` (sent on connect) |

## Findings Pack schema v1 (`/pack/pack.schema.json` + `/pack/findings-pack.v1.json`)

```jsonc
{
  "schema_version": 1,
  "generated_at": "ISO",
  "dataset": { "matches": 26036, "player_games": 260360, "patches": ["14.17","16.16"] },
  "findings": [ { "key": "mastery_premium", "tier": "actionable", "title": "...", "statement": "...", "value": 3.7, "unit": "pp", "source_ref": "companion-app-content.md#7" } ],
  "habits": [ { "key": "recall_safety", "label": "Recall safely", "effect_per_sd": 2.24 } ],   // 4 items, fixed keys: recall_safety, fast_first_dragon, spend_before_backing, plates_by_14
  "objectives": { "baron_pre25_win_rate": .814, "baron_comeback_lift_pp": 29.5, "dragon_denial_win_rate": .954, "first_dragon_pre20_win_rate": .603, "herald_pre20_win_rate": .666 },
  "comeback_odds": [ { "gold_deficit_at_15": -2000, "win_rate": .276 }, ... ],
  "ban_advisor": [ { "champion": "Lillia", "win_rate": .548, "ban_rate": .017, "recommendation": "real-threat" } ],
  "trap_picks": [ { "champion": "Hecarim", "win_rate": .415 } ],
  "tier_list": [ { "champion": "...", "role": "MIDDLE", "games": 340, "pick_rate": .142, "win_rate": .534, "tier": "S" } ],
  "matchup_examples": [ { "champion": "...", "opponent": "...", "role": "MIDDLE", "wr": .57, "ci": 2.1, "games": 41 } ],
  "benchmarks": [ { "role": "TOP", "cs10_median": 62, "level10_median": null, "gold10_median": null, "sample": 5000 } ],
  "checkpoints": [ { "gold_diff_bucket": "-1000..0 @20m", "win_rate": .282 } ]
}
```

Rules: every number traces to research docs (`source_ref`); Diagnostic content never phrased as advice (ADR-0003); missing tables → omit key, never invent (dashboard convention).

## Dev data

`data/dev-import/Gankruptcy-DADDY/*.json` holds real downloaded matches (LoLTrends layout). Backend `POST /dev/import {dir}` (debug builds only) ingests that folder into Personal History through the same extractor as Riot sync, tagged `mode:"import"`.

## Frontend conventions

- React 19 + TanStack Router (code routes) + TanStack Query. Tailwind v4 tokens in `src/styles.css` (`--color-*` mapped from design's `--rc-*` palette).
- API access only via `src/api/client.ts`; live only via `src/api/sse.ts`. No direct fetch elsewhere.
- Route paths: `/champ-select`, `/live`, `/postgame`, `/progress`, `/champions`, `/history`.
- Phrasing discipline (ADR-0003): actionable findings may instruct; diagnostic stats describe ("You were X", never "Do X").
