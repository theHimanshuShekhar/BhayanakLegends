# Bhayanak Legends v1 — Interface Contract

Single source of truth for frontend↔backend↔pack interfaces. Change here, not ad hoc.

## Process model

The sidecar requires an explicit `BHAYANAK_TOKEN` of at least 32 characters.
Missing, blank, short, and literal `dev` values fail startup before bind or
readiness output. All HTTP endpoints require `X-BL-Token: <token>`; missing or
invalid credentials return `401`. The only exception to header placement is
`/events`, which also accepts `?token=` because EventSource cannot set headers.

Every request must contain exactly one valid loopback `Host`: `localhost`,
`127.0.0.1`, or `[::1]`, with an optional port matching the actual listener
port. Missing, duplicate, malformed, userinfo-bearing, non-loopback, and
wrong-port hosts return `400 {"detail":"invalid host"}` before token checks.
The sidecar preserves CORS origins `http://localhost:1420` and
`tauri://localhost`. Access logs are disabled; retained request logs contain
only method and path and never query strings, headers, or credentials.

Frontend obtains `{port, token}` via Tauri command `sidecar_info`. In web-only
dev (`pnpm dev` without Tauri), defaults: port from `VITE_BL_PORT` (default
23110), token from `VITE_BL_TOKEN` (default
`local-sidecar-development-token-32chars`).

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
type Role = "TOP"|"JUNGLE"|"MIDDLE"|"BOTTOM"|"UTILITY"|"UNKNOWN";
type GameflowPhase = "None"|"Lobby"|"Matchmaking"|"RankedGame"|"ChampSelect"|"GameStart"|"InProgress"|"WaitingForStats"|"EndOfGame";
type GameMode = "CLASSIC"|"ODIN"|"ARAM"|"TUTORIAL"|"URF"|"ONEFORALL"|"DOOM_BOTS"|"ASCENSION"|"FIRSTBLOOD"|"KING_PORO"|"SIEGE"|"PROJECT"|"SNOWDOWN"|"NEXUSBLITZ"|"ULTBOOK"|"CHERRY";
interface Health { status: "ok"|"degraded"; app_version: string; pack_version: string|null; }
interface Settings {
  riot_id: string | null;        // "GameName#TAG"
  region_route: "sea" | "americas" | "europe" | "asia";
  has_key: boolean;              // never returns the key itself
  auto_sync: boolean;
}
interface SettingsPatch { riot_id?: string|null; region_route?: "sea"|"americas"|"europe"|"asia"; riot_key?: string|null; auto_sync?: boolean; }

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
interface RoleRow { role: Role; games: number; wins: number; }

interface TrajectoryPoint {
  patch: string; role: Role; champion: string | null;
  played_at: string; index: number; rolling_wr: number;
}
interface PatchAggregate {
  patch: string;
  games: number; wins: number; win_rate: number; // true counts from Personal History
}

interface PostGameDigest {
  match_id: string;
  played_at: string;
  champion: string; role: Role; win: boolean; duration_s: number;
  checkpoints: { gold_diff_10: number|null; gold_diff_15: number|null; gold_diff_20: number|null };
  habits: HabitOutcome[];         // only outcomes with an exact extractor + threshold; empty when unavailable
  headline: string;               // one-line takeaway, tier-respecting phrasing
}

Checkpoint missing-data rule: `cs10`, `level10`, and `gold_diff_10` are `null`
unless the match timeline contains a populated frame with a timestamp at or
after 600,000 ms, proving that the match reached ten minutes. Once proven,
each value uses the latest timeline frame at or before 600,000 ms; it is never
guessed or interpolated, and remains `null` when that selected frame lacks the
participant. The independent 15- and 20-minute lookups retain their
latest-at-or-before behavior.

// The backend never emits a permanent value="n/a"/verdict="n/a" row. A
// digest with no contracted habit outcome carries habits: [] and the UI says
// that habit evaluation is unavailable.
interface HabitOutcome { key: string; label: string; value: string; verdict: "good"|"bad"|"neutral"|"n/a"; }

interface RoleBenchmark {
  role: Role;
  personal: Partial<Record<"cs10"|"level10"|"gold_diff_10", number>>;
  population: Partial<Record<"cs10_median"|"level10_median"|"gold_diff_10_median", number>> & {
    sample: number;
  };
}

### Benchmark feature contract

This table is normative. A Benchmark may be emitted only for a row whose
personal extractor and Findings Pack population feature both equal the table's
canonical feature, whose units and eligible role are identical, and whose
missing-data rule is satisfied. The pack's `feature_contract` metadata declares
the source feature used for each population column; a missing or different
declaration suppresses that comparison. In particular, the shipped pack's
`lane_minions_first_10m` values are not total `cs10` and therefore never join.

| canonical name | unit | population feature | personal extractor | eligible roles | missing-data rule | source_ref |
|---|---|---|---|---|---|---|
| `cs10` | minions | `cs10` (total minions at 10m) | `cs10` (total minions at 10m) | TOP, JUNGLE, MIDDLE, BOTTOM, UTILITY | omit when either value is null/non-numeric, including when no populated frame proves ten-minute reachability | `docs/CONTRACT.md#benchmark-feature-contract` |
| `level10` | levels | `level10` (level at 10m) | `level10` (level at 10m) | TOP, JUNGLE, MIDDLE, BOTTOM, UTILITY | omit when either value is null/non-numeric, including when no populated frame proves ten-minute reachability | `docs/CONTRACT.md#benchmark-feature-contract` |
| `gold_diff_10` | gold | `gold_diff_10` (difference from same-frame ten-player median at 10m) | `gold_diff_10` (difference from same-frame ten-player median at 10m) | TOP, JUNGLE, MIDDLE, BOTTOM, UTILITY | omit when either value is null/non-numeric, including when no populated frame proves ten-minute reachability | `docs/CONTRACT.md#benchmark-feature-contract` |

interface LiveStatus {
  champ_select: { active: boolean; phase: GameflowPhase|null };
  ingame: { active: boolean; game_id: number|null; mode: GameMode|null; clock_s: number };
  last_error: string | null;
}

// Rich LCU-bridge snapshots (GET /live/session + SSE "champselect.state").
// COMPLIANCE: enemy summoner names are stripped at the service layer —
// ChampSelectSnapshot.enemy[].name is always null.
interface ChampSelectBan { champion_id: number; champion: string|null }   // champion null → UI shows "Champion {id}"
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
  phase: GameflowPhase|null;      // LCU gameflow phase
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
  name: "GameStart"|"MinionsSpawning"|"FirstBrick"|"DragonKill"|"HeraldKill"|"BaronKill"|"ChampionKill"|"TurretKilled"|"InhibKilled"|"GameEnd";
  t_s: number;                   // EventTime
  actor: string|null; victim: string|null;
  detail: string|null;           // DragonType on DragonKill
}
interface InGameSnapshot {
  active: boolean;
  clock_s: number;               // gameData.gameTime; client ticks between frames
  mode: GameMode|null;
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
| `pack.updated` | `{schema_version, pack_version}` |
| `hello` | `{app_version, pack_version}` (sent on connect) |

## Findings Pack schema v1 (bundled seed and active pack)
The packaged `/pack/pack.schema.json` and `/pack/findings-pack.v1.json` files
are an immutable first-run seed. On startup, the sidecar validates and
atomically copies that seed to the durable active directory
`<data_dir>/findings-pack/active` when no active pack exists. Explicit release
activation and all runtime reads use only that active directory; an existing
active pack wins over a changed bundled seed. The pack response includes
`pack_version` (defaulting to `v1` for the seed), and Health, `/pack`, and the
`hello`/`pack.updated` events expose the active version.

### Table-level provenance

Every numeric-bearing table in the pack has an entry in the root `provenance`
map. The block is table-level (not repeated on numeric leaves) and is required
by `pack/pack.schema.json`:

```ts
interface TableProvenance {
  source_document: string;
  source_section: string;
  feature_store_manifest_sha256: string; // lowercase SHA-256 hex
  generator_revision: string;             // sha256:<64 lowercase hex>
  feature_contract_version: "loltrends-parity-v1";
}
interface PackProvenance {
  dataset: TableProvenance;
  findings: TableProvenance;
  habits: TableProvenance;
  objectives: TableProvenance;
  comeback_odds: TableProvenance;
  ban_advisor: TableProvenance;
  trap_picks: TableProvenance;
  tier_list: TableProvenance;
  matchup_examples: TableProvenance;
  benchmarks: TableProvenance;
  checkpoints: TableProvenance;
}
```

`pack/findings-pack.v1.json` is generated only by
`backend/tools/build_pack.py`; builds require an explicit `--feature-store`
path. The generator hashes the declared Feature Store inputs and its own
source, so a pack records the exact data snapshot and generator revision.
Findings retain their per-finding `source_ref` in addition to the table-level
provenance.

Rules: every number traces to research docs (`source_ref`) or a table
provenance block; Diagnostic content never phrased as advice (ADR-0003);
missing tables → omit key, never invent (dashboard convention).

## Dev data

`data/dev-import/Gankruptcy-DADDY/*.json` holds real downloaded matches (LoLTrends layout). Backend `POST /dev/import {dir}` is available only to non-frozen debug sidecars when `BHAYANAK_ALLOW_IMPORT=true` and `BHAYANAK_IMPORT_ROOTS` is a non-empty JSON array of existing, canonical approved directory roots. The requested directory must already exist beneath one of those roots; symlink escapes and traversal outside the roots are rejected. The endpoint ingests an approved folder into Personal History through the same extractor as Riot sync, tagged `mode:"import"`.

## Frontend conventions

- React 19 + TanStack Router (code routes) + TanStack Query. Tailwind v4 tokens in `src/styles.css` (`--color-*` mapped from design's `--rc-*` palette).
- API access only via `src/api/client.ts`; live only via `src/api/sse.ts`. No direct fetch elsewhere.
- Route paths: `/champ-select`, `/live`, `/postgame`, `/progress`, `/champions`, `/history`.
- Phrasing discipline (ADR-0003): actionable findings may instruct; diagnostic stats describe ("You were X", never "Do X").
