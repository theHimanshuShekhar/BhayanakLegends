"""Pydantic models mirroring docs/CONTRACT.md.

The API deliberately uses closed literals and nested models.  Returning an
unvalidated ``dict`` from a route makes a contract drift invisible until a
frontend crashes, so response models reject unknown states and shapes.
"""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field



class ContractModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


RegionRoute = Literal["sea", "americas", "europe", "asia"]
Role = Literal["TOP", "JUNGLE", "MIDDLE", "BOTTOM", "UTILITY", "UNKNOWN"]
AssignedRole = Literal["TOP", "JUNGLE", "MIDDLE", "BOTTOM", "UTILITY"]
SyncState = Literal["idle", "running", "cancelled", "error"]
SyncMode = Literal["era_first", "import"]
OwnerState = Literal["unassigned", "resolving", "active", "error"]
HealthStatus = Literal["ok", "degraded"]
GameflowPhase = Literal[
    "None",
    "Lobby",
    "Matchmaking",
    "RankedGame",
    "ChampSelect",
    "GameStart",
    "InProgress",
    "WaitingForStats",
    "EndOfGame",
]
GameMode = Literal[
    "CLASSIC",
    "ODIN",
    "ARAM",
    "TUTORIAL",
    "URF",
    "ONEFORALL",
    "DOOM_BOTS",
    "ASCENSION",
    "FIRSTBLOOD",
    "KING_PORO",
    "SIEGE",
    "PROJECT",
    "SNOWDOWN",
    "NEXUSBLITZ",
    "ULTBOOK",
    "CHERRY",
]
CellState = Literal["intent", "picked", "hover", "locked", "none"]
HabitVerdict = Literal["good", "bad", "neutral", "n/a"]
BenchmarkMetric = Literal["cs10", "level10", "gold_diff_10"]
BenchmarkState = Literal["available", "contract-suppressed", "insufficient-personal-history"]
LiveEventName = Literal[
    "GameStart",
    "MinionsSpawning",
    "FirstBrick",
    "DragonKill",
    "HeraldKill",
    "BaronKill",
    "ChampionKill",
    "TurretKilled",
    "InhibKilled",
    "GameEnd",
]


class Health(ContractModel):
    status: HealthStatus
    app_version: str
    pack_version: str | None = None

class Settings(ContractModel):
    riot_id: str | None = None
    region_route: RegionRoute = "sea"
    has_key: bool = False
    auto_sync: bool = False
    # Opaque namespace and monotonic transition marker. The PUUID itself is
    # local-only and is never part of the HTTP contract.
    owner_key: str | None = None
    generation: int = Field(default=0, ge=0)
    owner_state: OwnerState = "unassigned"
    owner_error: str | None = None


class SettingsPatch(ContractModel):
    riot_id: str | None = None
    region_route: RegionRoute | None = None
    riot_key: str | None = None
    auto_sync: bool | None = None


class SyncStatus(ContractModel):
    state: SyncState = "idle"
    mode: SyncMode = "era_first"
    total_queued: int = Field(default=0, ge=0)
    downloaded: int = Field(default=0, ge=0)
    skipped: int = Field(default=0, ge=0)
    failed: int = Field(default=0, ge=0)
    current_match_id: str | None = None
    started_at: str | None = None
    owner_key: str | None = None
    generation: int = Field(default=0, ge=0)
    owner_state: OwnerState = "unassigned"
    owner_error: str | None = None



class RoleRow(ContractModel):
    role: Role
    games: int = Field(ge=0)
    wins: int = Field(ge=0)


class HistorySummary(ContractModel):
    matches: int = Field(ge=0)
    patches: list[str]
    by_role: list[RoleRow]
    win_rate: float = Field(ge=0, le=1)


class TrajectoryPoint(ContractModel):
    patch: str
    role: Role
    champion: str | None = None
    played_at: str
    index: int = Field(ge=0)
    rolling_wr: float = Field(ge=0, le=1)


class PatchAggregate(ContractModel):
    patch: str
    games: int = Field(ge=0)
    wins: int = Field(ge=0)
    win_rate: float = Field(ge=0, le=1)


class HabitOutcome(ContractModel):
    key: str
    label: str
    value: str
    verdict: HabitVerdict


InsightState = Literal["empty", "available"]
InsightSampleStatus = Literal["insufficient", "review"]
InsightWindowCompleteness = Literal["full", "partial", "unavailable"]


class RoleInsight(ContractModel):
    role: Role
    games: int = Field(ge=0)
    wins: int = Field(ge=0)
    win_rate: float = Field(ge=0, le=1)
    sample_status: InsightSampleStatus


class ChampionInsight(ContractModel):
    champion: str
    games: int = Field(ge=0)
    wins: int = Field(ge=0)
    win_rate: float = Field(ge=0, le=1)
    roles: list[Role]
    sample_status: InsightSampleStatus


class InsightFilters(ContractModel):
    role: Role | None = None
    champion: str | None = None


class InsightWindow(ContractModel):
    name: Literal["latest", "preceding"]
    games: int = Field(ge=0)
    wins: int = Field(ge=0)
    win_rate: float = Field(ge=0, le=1)
    sample_status: InsightSampleStatus
    completeness: InsightWindowCompleteness


class HistoryInsights(ContractModel):
    state: InsightState
    sample_size: int = Field(ge=0)
    filters: InsightFilters
    roles: list[RoleInsight]
    champions: list[ChampionInsight]
    windows: dict[Literal["latest", "preceding"], InsightWindow]
    feature_contract_version: str | None = None
    feature_contract_status: Literal["available", "mixed", "unavailable"] = "unavailable"


class TeamState(ContractModel):
    feature: Literal["team_gold_diff_15m"] = "team_gold_diff_15m"
    feature_contract_version: str = "loltrends-parity-v2"
    team_gold_diff_15m: float | None = None
    observed_through_s: float | None = Field(default=None, ge=0)
    non_surrendered: bool | None = None


class Checkpoints(ContractModel):
    gold_diff_10: float | None = None
    gold_diff_15: float | None = None
    gold_diff_20: float | None = None


PersonalHistoryEligibility = Literal["eligible", "ineligible", "unknown"]


class PostGameDigest(ContractModel):
    match_id: str
    played_at: str
    champion: str
    role: Role
    win: bool
    duration_s: int = Field(ge=0)
    checkpoints: Checkpoints
    habits: list[HabitOutcome]
    headline: str
    feature_contract_version: str | None = None
    personal_history_eligibility: PersonalHistoryEligibility = "unknown"
    features: dict[str, float | None] = Field(default_factory=dict)
    team_state: TeamState | None = None


LiveInferenceStatus = Literal[
    "available",
    "suppressed",
    "stale",
    "incompatible",
    "unsupported-patch",
    "out-of-domain",
    "error",
]


class LiveInference(ContractModel):
    status: LiveInferenceStatus = "suppressed"
    probability: float | None = Field(default=None, ge=0, le=1)
    observed_game_time_s: float | None = Field(default=None, ge=0)
    model_version: str | None = None
    pack_version: str | None = None
    reason: str | None = None


class LiveEventDelta(ContractModel):
    event_id: str
    source_order: int = Field(ge=0)
    name: LiveEventName
    t_s: float = Field(ge=0)
    baseline_probability: float | None = Field(default=None, ge=0, le=1)
    event_probability: float | None = Field(default=None, ge=0, le=1)
    delta_probability: float | None = Field(default=None, ge=-1, le=1)
    pre_observed_game_time_s: float | None = Field(default=None, ge=0)
    post_observed_game_time_s: float | None = Field(default=None, ge=0)
    model_version: str | None = None
    pack_version: str | None = None
    suppression_status: LiveInferenceStatus = "suppressed"
    reason: str | None = None


WhatIfStatus = Literal[
    "available",
    "suppressed",
    "rejected",
    "unsupported-patch",
    "out-of-domain",
    "error",
]
class WhatIfRequest(ContractModel):
    adjustments: dict[str, float] = Field(default_factory=dict)


class WhatIfResponse(ContractModel):
    status: WhatIfStatus = "suppressed"
    probability: float | None = Field(default=None, ge=0, le=1)
    baseline_probability: float | None = Field(default=None, ge=0, le=1)
    adjusted_features: dict[str, float] | None = None
    model_version: str | None = None
    pack_version: str | None = None
    rejected_fields: list[str] = Field(default_factory=list)
    reason: str | None = None



class RoleBenchmarkPersonal(ContractModel):
    cs10: float | None = None
    level10: float | None = None
    gold_diff_10: float | None = None


class RoleBenchmarkPopulation(ContractModel):
    cs10_median: float | None = None
    level10_median: float | None = None
    gold_diff_10_median: float | None = None
    sample: int = Field(ge=0)


class RoleBenchmark(ContractModel):
    role: Role
    personal: RoleBenchmarkPersonal
    population: RoleBenchmarkPopulation


class BenchmarkResponse(ContractModel):
    state: BenchmarkState
    rows: list[RoleBenchmark]

class LiveState(ContractModel):
    """Combined internal state shape for callers that need both fields."""

    active: bool = False
    phase: GameflowPhase | None = None
    game_id: int | None = None
    mode: GameMode | None = None
    clock_s: int = Field(default=0, ge=0)


class ChampSelectStatus(ContractModel):
    active: bool = False
    phase: GameflowPhase | None = None


class InGameStatus(ContractModel):
    active: bool = False
    game_id: int | None = None
    mode: GameMode | None = None
    clock_s: int = Field(default=0, ge=0)


class LiveStatus(ContractModel):
    champ_select: ChampSelectStatus
    ingame: InGameStatus
    last_error: str | None = None

class ChampSelectBan(ContractModel):
    champion_id: int = 0
    champion: str | None = None


class CsBan(ChampSelectBan):
    """Internal name retained for the live bridge's ban collection."""


class AllyCell(ContractModel):
    cell_id: int = 0
    champion_id: int = 0
    champion: str | None = None
    name: str | None = None
    is_local: bool = False
    state: CellState = "none"


class EnemyCell(ContractModel):
    cell_id: int = 0
    champion_id: int = 0
    champion: str | None = None
    name: str | None = None
    state: CellState = "none"


class ChampSelectSnapshot(ContractModel):
    active: bool = False
    phase: GameflowPhase | None = None
    timer_sec: int | None = None
    local_assigned_role: AssignedRole | None = None
    bans_ally: list[CsBan] = Field(default_factory=list)
    bans_enemy: list[CsBan] = Field(default_factory=list)
    ally: list[AllyCell] = Field(default_factory=list)
    enemy: list[EnemyCell] = Field(default_factory=list)
