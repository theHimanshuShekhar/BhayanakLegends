# Bhayanak Legends v2 — Interface Contract

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

## REST API (v2)

Base URL: `http://127.0.0.1:{port}`

| Method | Path | Response | Notes |
|---|---|---|---|
| GET | /health | `Health` | liveness + versions |
| GET | /pack | `FindingsPackV2` | full pack JSON (validated v2 contract) |
| PUT | /settings | `Settings` | body: partial `SettingsPatch` |
| POST | /sync/start | `SyncStatus` | kicks era-first backfill (no-op if running) |
| POST | /sync/cancel | `SyncStatus` | |
| GET | /sync/status | `SyncStatus` | |
| GET | /progress/aggregates | `PatchAggregate[]` | true Personal History patch aggregates; query: `patch?`, `role?`, `champion?` |
| GET | /progress/trajectories | `TrajectoryPoint[]` | per-match rolling line; query: `patch?`, `role?`, `champion?` |
| GET | /postgame/latest | `PostGameDigest \| null` | null = none yet |
| GET | /benchmarks | `BenchmarkResponse` | stateful population/personal comparisons |
| GET | /history/insights | `HistoryInsights` | contract-aware Personal History insights |
| POST | /history/what-if | `WhatIfResponse` | local, model-card-gated personal what-if |
| GET | /history/summary | `HistorySummary` | true Personal History summary; empty history → `{matches:0, patches:[], by_role:[], win_rate:0}` |
| GET | /live/status | `LiveStatus` | coarse LCU + in-game health |
| GET | /live/session | `ChampSelectSnapshot` | rich champ-select state; idle → `{active:false,...}` |
| GET | /live/ingame | `InGameSnapshot` | rich in-game state; idle → `{active:false,...}` |
| GET | /events | SSE stream | see Events |

### Types (mirrored in `src/api/types.ts`; python side in `bhayanak_legends.models`)

```ts
type Role = "TOP"|"JUNGLE"|"MIDDLE"|"BOTTOM"|"UTILITY"|"UNKNOWN";
type AssignedRole = "TOP"|"JUNGLE"|"MIDDLE"|"BOTTOM"|"UTILITY";
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
  feature_contract_version: string|null;
  personal_history_eligibility: PersonalHistoryEligibility;
  features: Record<string, number|null>;
  team_state: TeamState|null;
}

type PersonalHistoryEligibility = "eligible"|"ineligible"|"unknown";
interface TeamState {
  feature: "team_gold_diff_15m";
  feature_contract_version: "loltrends-parity-v2";
  team_gold_diff_15m: number|null;
  observed_through_s: number|null;
  non_surrendered: boolean|null;
}

interface InsightWindow {
  name: "latest"|"preceding";
  games: number;
  wins: number;
  win_rate: number;
  sample_status: "insufficient"|"review";
  completeness: "full"|"partial"|"unavailable";
}
interface HistoryInsights {
  state: "empty"|"available";
  sample_size: number;
  filters: { role: Role|null; champion: string|null };
  roles: RoleInsight[];
  champions: ChampionInsight[];
  windows: { latest: InsightWindow; preceding: InsightWindow };
  feature_contract_version: string|null;
  feature_contract_status: "available"|"mixed"|"unavailable";
}
interface RoleInsight {
  role: Role; games: number; wins: number; win_rate: number;
  sample_status: "insufficient"|"review";
}
interface ChampionInsight {
  champion: string; games: number; wins: number; win_rate: number;
  roles: Role[]; sample_status: "insufficient"|"review";
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

interface BenchmarkResponse {
  state: "available"|"contract-suppressed"|"insufficient-personal-history";
  rows: RoleBenchmark[];
}

interface RoleBenchmark {
  role: Role;
  personal: Partial<Record<"cs10"|"level10"|"gold_diff_10", number>>;
  population: Partial<Record<"cs10_median"|"level10_median"|"gold_diff_10_median", number>> & {
    sample: number;
  };
}
`contract-suppressed` means no finite Findings Pack population cell passes
the canonical feature, declaration, role, and eligibility checks. When at
least one compatible cell exists but no same-definition finite Personal
History median can be emitted, the state is
`insufficient-personal-history`. `available` requires one or more rows; all
unavailable states carry `rows: []`. A Findings Pack load or validation
failure remains the authenticated API's bounded 503 error and is not a
benchmark state.

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
  state: "intent"|"picked"|"hover"|"locked"|"none";
}
interface ChampSelectEnemyCell {
  cell_id: number;
  champion_id: number;
  champion: string|null;
  name: string|null;             // always null — compliance
  state: "intent"|"picked"|"hover"|"locked"|"none";
}
interface ChampSelectSnapshot {
  active: boolean;
  phase: GameflowPhase|null;      // LCU gameflow phase
  timer_sec: number|null;         // adjustedTimeLeftInSec; client ticks down between frames
  local_assigned_role: AssignedRole|null; // local participant assignedPosition; null when absent/unrecognized
  bans_ally: ChampSelectBan[];
  bans_enemy: ChampSelectBan[];
  ally: ChampSelectAllyCell[];
  enemy: ChampSelectEnemyCell[];
}

`local_assigned_role` is normalized only from the local participant's
`assignedPosition` (case-insensitive); missing, empty, `UNKNOWN`, and
unrecognized values are `null`. `locked` is emitted only for the local cell
when a completed local `pick` action identifies that cell and both action and
participant champion IDs are nonzero and agree. A nonzero champion without
completed action evidence remains `picked`; malformed or incomplete evidence
never implies `locked`. Idle and reconnect snapshots clear the role and lock
evidence.

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

type LiveInferenceStatus = "available"|"suppressed"|"stale"|"incompatible"|"unsupported-patch"|"out-of-domain"|"error";
interface LiveInference {
  status: LiveInferenceStatus;
  probability: number|null;
  observed_game_time_s: number|null;
  model_version: string|null;
  pack_version: string|null;
  reason: string|null;
}
interface LiveEventDelta {
  event_id: string;
  source_order: number;
  name: LiveEvent["name"];
  t_s: number;
  baseline_probability: number|null;
  event_probability: number|null;
  delta_probability: number|null;
  pre_observed_game_time_s: number|null;
  post_observed_game_time_s: number|null;
  model_version: string|null;
  pack_version: string|null;
  suppression_status: LiveInferenceStatus;
  reason: string|null;
}
interface WhatIfRequest { adjustments: Record<string, number>; }
interface WhatIfResponse {
  status: "available"|"suppressed"|"rejected"|"unsupported-patch"|"out-of-domain"|"error";
  probability: number|null;
  baseline_probability: number|null;
  adjusted_features: Record<string, number>|null;
  model_version: string|null;
  pack_version: string|null;
  rejected_fields: string[];
  reason: string|null;
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
## Findings Pack schema v2 (bundled seed and active pack)
The packaged `/pack/pack.schema.json` and `/pack/findings-pack.v2.json` files
are copied by `backend/tools/build_pack.py`, which is a consumer-side
validation bridge rather than a population producer. LoLTrends is the sole
producer of population evidence. A release build must pass an explicitly
supplied `--artifact` path containing the exported
`findings-pack.v2.json`; `--bootstrap` only copies the checked-in diagnostic
seed when an upstream artifact is unavailable. Bhayanak never reads LoLTrends
Feature Store files and never computes, fills, renames, or translates
population fields.

The bridge validates the supplied artifact against the canonical schema and
strict `FindingsPackV2` semantics before copying it. An artifact that uses a
different root/table shape (including the current LoLTrends research-side
catalog/export shape) fails closed with the exact contract mismatch; it is not
translated into the companion schema. The output schema is the unchanged
consumer schema generated from `bhayanak_legends.pack_v2.FindingsPackV2`.
The active directory is populated atomically from the bundled seed on first
startup; an existing active pack wins over a changed bundled seed.

### Cross-repo artifact blocker
The currently inspected LoLTrends `findings_pack.py` exporter is not an
acceptable input to this bridge yet. Its research-side payload has a
`dataset.player_games` field instead of the companion
`dataset.participant_performances`, adds a root `benchmarks` table, and emits
additional fields such as `source_subsection` that the closed Bhayanak v2
models reject. This is an exact contract mismatch, not a missing-value case;
Bhayanak intentionally fails closed until LoLTrends publishes an artifact
matching the companion schema. No adapter or field translation belongs in this
repository.

The v2 root has `schema_version: 2`, a patch range of `14.17` through `16.17`,
and the following discriminated evidence collections:
`findings`, `habits`, `objectives`, `comeback_odds`, `ban_context`,
`tier_list`, `matchup_examples`, `checkpoints`, `route_archetypes`, and
`build_evidence`. Every row has patch scope, population scope, era-stability,
caveats, source document/section/reference, provenance key, tier, and an
explicit release status. `available` rows contain finite values and positive
samples; `withheld` and `superseded` rows contain no value and explain their
release reason. Diagnostic rows never use recommendation language.

### Findings Pack v2 feature contracts
`feature_contracts.population`, `feature_contracts.personal_history`, and
`feature_contracts.models` declare the exact definitions used by each table.
Provenance rows must reference one of those declared versions; a consumer must
not join rows solely because a field has a similar name.

The v2 Personal History feature order is:
`cs10`, `level10`, `gold_diff_10`, `team_gold_diff_15m`,
`recalls_before_15m`, `avg_banked_gold_at_recall_by_15m`,
`avg_banked_gold_at_recall_by_20m`, `unseen_recall_share_by_15m`,
`unseen_recall_share_by_20m`, `first_dragon_by_20m_s`,
`first_riftherald_by_20m_s`, `first_baron_by_20m_s`,
`smite_contests_before_15m`, `smite_contests_before_20m`,
`early_fight_participation_rate`, and `plates_taken_by_14m`.
`team_gold_diff_15m` is the latest exact frame at or before 900 seconds after
a later frame proves the match reached 900 seconds. It is the player's team
gold minus the opposing team's gold, requires all ten participants and a
non-surrendered match, and is never midpointed, clipped, extrapolated, or
replaced by a personal gold field.

`comeback_odds` is exactly three `team_gold_diff_15m` bands:
`[2000,3000)`, `[3000,5000)`, and `[5000,∞)`. Exact 3000 belongs to the
second band and exact 5000 to the third. Every available band has a finite
rate and positive sample. When exact Feature Store evidence is unavailable,
the rows remain explicitly withheld with null rates and zero samples.

The bundled diagnostic seed copies the LoLTrends handoff: 125,031 eligible
matches, 1,250,310 participant performances, 175 criteria-admitted tracked
players, and 49 patch buckets across 14.17–16.17. Bhayanak does not derive
those values. Its Surrender Advisor is withheld because the observed
22.7 percentage-point gap exceeds the five-point tolerance. Baron comeback lift
is omitted. Route archetypes are approximate diagnostics, not advice; build
evidence is withheld and contains no raw sequence rows. A number is emitted
only when the producer artifact or checked-in diagnostic seed supplies the
corresponding evidence.

### Model and artifact contract
`models` is keyed by stable model name. A declaration is either available
with an ONNX artifact and matching model card, or suppressed with a release
reason and no executable fields. Model cards contain an explicit
`feature_contract_version` (predictive personal cards must declare
`loltrends-cutoff-v2`), exact ordered `float32` inputs, units, sources,
adjustable flags, bounds, preprocessing, patch scope, validation gates,
caveats, and a smoke-test vector. Runtime inference accepts only finite values
matching the card exactly, rejects unknown or missing fields and out-of-domain
values, and never loads pickle artifacts. Available artifact paths, hashes,
sizes, and card files are verified before activation; model directories cannot
contain undeclared artifacts. The personal what-if model key is
`personal_what_if`, and the live win-probability model key is `live_wp`.

`InGameSnapshot.inference.status` is one of `available`, `suppressed`,
`stale`, `incompatible`, `unsupported-patch`, `out-of-domain`, or `error`.
Probability, model version, pack version, and observed time are nullable and
omitted unless the status supports them. `event_deltas` contain one correlated
entry for each supported live event kind (`DragonKill`, `HeraldKill`,
`BaronKill`, and `TurretKilled`) once observed. Each entry carries stable
`event_id`/`source_order`, causal pre/post observation times, model/pack
provenance, and a nullable `delta_probability`; `suppression_status` and
`reason` distinguish an unavailable delta from an exact zero movement.
Unsupported event kinds stay in `events` but do not create delta entries.
No live probability is inferred from clock time alone.

`POST /history/what-if` accepts only local JSON
`{"adjustments": Record<string, number>}`. The backend accepts exactly the
card-declared adjustable fields, requires a complete finite baseline, and
rejects unknown, missing, non-finite, and out-of-domain values without
clipping or extrapolation. Its response reports `available` with a
probability only after successful local ONNX inference, or a truthful
`suppressed`/`rejected`/`error` status with nullable probability and a reason.

### Table-level provenance
Every numeric-bearing table has an entry in the root `provenance` map:

```ts
interface TableProvenance {
  source_document: string;
  source_section: string;
  source_ref: string;
  feature_store_manifest_sha256: string; // lowercase SHA-256 hex
  generator_revision: string;             // sha256:<64 lowercase hex>
  feature_contract_version: string;       // must be declared in feature_contracts
}
```

Rules: every number traces to research docs (`source_ref`) or a table
provenance block; diagnostic content never becomes advice; missing or
incompatible evidence is represented by omission or an explicit suppressed
state. Personal History rows are owner-scoped by resolved PUUID and match
identity; no ownerless fallback is permitted.

## Dev data

`data/dev-import/FixturePlayer03-BL03/*.json` holds downloaded matches (LoLTrends layout) with pseudonymized identities. Backend `POST /dev/import {dir}` is available only to non-frozen debug sidecars when `BHAYANAK_ALLOW_IMPORT=true` and `BHAYANAK_IMPORT_ROOTS` is a non-empty JSON array of existing, canonical approved directory roots. The requested directory must already exist beneath one of those roots; symlink escapes and traversal outside the roots are rejected. The endpoint ingests an approved folder into Personal History through the same extractor as Riot sync, tagged `mode:"import"`.

## Frontend conventions

- React 19 + TanStack Router (code routes) + TanStack Query. Tailwind v4 tokens in `src/styles.css` (`--color-*` mapped from design's `--rc-*` palette).
- API access only via `src/api/client.ts`; live only via `src/api/sse.ts`. No direct fetch elsewhere.
- Route paths: `/champ-select`, `/live`, `/postgame`, `/progress`, `/champions`, `/history`.
- Phrasing discipline (ADR-0003): actionable findings may instruct; diagnostic stats describe ("You were X", never "Do X").
