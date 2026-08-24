"""Pydantic models mirroring docs/CONTRACT.md.

The API deliberately uses closed literals and nested models.  Returning an
unvalidated ``dict`` from a route makes a contract drift invisible until a
frontend crashes, so response models reject unknown states and shapes.
"""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class ContractModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


FindingTier = Literal["actionable", "diagnostic", "a-lite"]
RegionRoute = Literal["sea", "americas", "europe", "asia"]
Role = Literal["TOP", "JUNGLE", "MIDDLE", "BOTTOM", "UTILITY", "UNKNOWN"]
SyncState = Literal["idle", "running", "cancelled", "error"]
SyncMode = Literal["era_first", "import"]
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
CellState = Literal["intent", "picked", "hover", "none"]
HabitVerdict = Literal["good", "bad", "neutral", "n/a"]
BenchmarkMetric = Literal["cs10", "level10", "gold_diff_10"]
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


class Checkpoints(ContractModel):
    gold_diff_10: float | None = None
    gold_diff_15: float | None = None
    gold_diff_20: float | None = None


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


class LiveState(ContractModel):
    """Legacy internal state shape used by callers that need both fields."""

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


class TableProvenance(ContractModel):
    source_document: str
    source_section: str
    feature_store_manifest_sha256: str
    generator_revision: str
    feature_contract_version: Literal["loltrends-parity-v1"]


class PackProvenance(ContractModel):
    dataset: TableProvenance
    findings: TableProvenance
    habits: TableProvenance
    objectives: TableProvenance
    comeback_odds: TableProvenance
    ban_advisor: TableProvenance
    trap_picks: TableProvenance
    tier_list: TableProvenance
    matchup_examples: TableProvenance
    benchmarks: TableProvenance
    checkpoints: TableProvenance


class PackFinding(ContractModel):
    key: str
    tier: FindingTier
    title: str
    statement: str
    value: float | None = None
    unit: str | None = None
    source_ref: str


class HabitDefinition(ContractModel):
    key: str
    label: str
    effect_per_sd: float


class BanAdvice(ContractModel):
    champion: str
    win_rate: float
    ban_rate: float
    recommendation: Literal["real-threat", "fear-ban", "skip"]


class TrapPick(ContractModel):
    champion: str
    win_rate: float


class TierEntry(ContractModel):
    champion: str
    role: Role
    games: int = Field(ge=0)
    pick_rate: float
    win_rate: float
    tier: Literal["S", "A", "B", "C"]


class MatchupExample(ContractModel):
    champion: str
    opponent: str
    role: Role
    wr: float
    ci: float
    games: int = Field(ge=0)


class PackFeatureContract(ContractModel):
    cs10_median: Literal["cs10", "lane_minions_first_10m"]
    level10_median: Literal["level10"]
    gold_diff_10_median: Literal["gold_diff_10"]


class PackBenchmark(ContractModel):
    role: Role
    cs10_median: float | None = None
    level10_median: float | None = None
    gold_diff_10_median: float | None = None
    feature_contract: PackFeatureContract
    sample: int = Field(ge=0)


class DatasetSummary(ContractModel):
    matches: int = Field(ge=0)
    player_games: int = Field(ge=0)
    patches: list[str]


class ComebackOdds(ContractModel):
    gold_deficit_at_15: float
    win_rate: float
class CheckpointBucket(ContractModel):
    gold_diff_bucket: str
    win_rate: float


class FindingsPack(ContractModel):
    schema_version: Literal[1]
    generated_at: str
    provenance: PackProvenance
    dataset: DatasetSummary
    findings: list[PackFinding]
    habits: list[HabitDefinition]
    objectives: dict[str, float]
    comeback_odds: list[ComebackOdds]
    ban_advisor: list[BanAdvice]
    trap_picks: list[TrapPick]
    tier_list: list[TierEntry]
    matchup_examples: list[MatchupExample]
    benchmarks: list[PackBenchmark]
    checkpoints: list[CheckpointBucket]
