"""Pydantic models mirroring docs/CONTRACT.md.

The API deliberately uses closed literals and nested models.  Returning an
unvalidated ``dict`` from a route makes a contract drift invisible until a
frontend crashes, so response models reject unknown states and shapes.
"""

import math
from math import isfinite
from typing import Any, Literal

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    FiniteFloat,
    StrictInt,
    model_validator,
)


class ContractModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


FindingTier = Literal["actionable", "diagnostic", "a-lite"]
RegionRoute = Literal["sea", "americas", "europe", "asia"]
Role = Literal["TOP", "JUNGLE", "MIDDLE", "BOTTOM", "UTILITY", "UNKNOWN"]
AssignedRole = Literal["TOP", "JUNGLE", "MIDDLE", "BOTTOM", "UTILITY"]
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


class BenchmarkResponse(ContractModel):
    state: BenchmarkState
    rows: list[RoleBenchmark]

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


class PackModel(ContractModel):
    """Forward-compatible model base for Findings Pack payloads."""

    model_config = ConfigDict(extra="ignore")


class TableProvenance(PackModel):
    source_document: str
    source_section: str
    feature_store_manifest_sha256: str
    generator_revision: str
    feature_contract_version: Literal["loltrends-parity-v1"]


class ComebackFeatureContract(PackModel):
    feature: str = Field(min_length=1)
    feature_contract_version: str = Field(min_length=1)

    def is_compatible(self) -> bool:
        return (
            self.feature == "gold_diff_15"
            and self.feature_contract_version == "loltrends-parity-v1"
        )


class PackProvenance(PackModel):
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


class PackFinding(PackModel):
    key: str
    tier: FindingTier
    title: str
    statement: str
    value: float | None = None
    unit: str | None = None
    source_ref: str


class HabitDefinition(PackModel):
    key: str
    label: str
    effect_per_sd: float


class BanAdvice(PackModel):
    champion: str
    win_rate: float
    ban_rate: float
    recommendation: Literal["real-threat", "fear-ban", "skip"]


class TrapPick(PackModel):
    champion: str
    win_rate: float


class TierEntry(PackModel):
    champion: str
    role: Role
    games: int = Field(ge=0)
    pick_rate: float
    win_rate: float
    tier: Literal["S", "A", "B", "C"]


class MatchupExample(PackModel):
    champion: str
    opponent: str
    role: Role
    wr: float
    ci: float
    games: int = Field(ge=0)


class PackFeatureContract(PackModel):
    cs10_median: Literal["cs10", "lane_minions_first_10m"] | None = None
    level10_median: Literal["level10"] | None = None
    gold_diff_10_median: Literal["gold_diff_10"] | None = None

    @model_validator(mode="after")
    def require_declaration(self) -> "PackFeatureContract":
        if not any((self.cs10_median, self.level10_median, self.gold_diff_10_median)):
            raise ValueError("feature_contract must declare at least one benchmark feature")
        return self

class PackBenchmark(PackModel):
    role: Role
    cs10_median: float | None = None
    level10_median: float | None = None
    gold_diff_10_median: float | None = None
    feature_contract: PackFeatureContract
    sample: int = Field(gt=0)

    @model_validator(mode="before")
    @classmethod
    def reject_explicit_nulls(cls, value: Any) -> Any:
        if isinstance(value, dict):
            for field in ("cs10_median", "level10_median", "gold_diff_10_median"):
                if field in value and value[field] is None:
                    raise ValueError(f"{field} must be omitted when unavailable")
        return value

    @model_validator(mode="after")
    def require_matching_declarations(self) -> "PackBenchmark":
        for field in ("cs10_median", "level10_median", "gold_diff_10_median"):
            median = getattr(self, field)
            declaration = getattr(self.feature_contract, field)
            if (median is None) != (declaration is None):
                raise ValueError(f"{field} median and declaration must be paired")
            if median is not None and not isfinite(median):
                raise ValueError(f"{field} median must be finite")
        return self


class DatasetSummary(PackModel):
    matches: int = Field(ge=0)
    player_games: int = Field(ge=0)
    patches: list[str]


class ComebackOdds(ContractModel):
    gold_deficit_at_15: StrictInt
    win_rate: FiniteFloat = Field(ge=0, le=1)


class CheckpointBucket(ContractModel):
    gold_diff_bucket: Literal["bottom_quartile_@20m", "top_quartile_@20m"]
    win_rate: FiniteFloat = Field(ge=0, le=1)


class FindingsPack(PackModel):
    schema_version: Literal[1]
    pack_version: str = Field(default="v1", min_length=1)
    generated_at: str
    comeback_feature_contract: ComebackFeatureContract
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

    @model_validator(mode="after")
    def validate_pack_contract(self) -> "FindingsPack":
        checkpoint_keys = [row.gold_diff_bucket for row in self.checkpoints]
        if len(checkpoint_keys) != 2 or set(checkpoint_keys) != {
            "bottom_quartile_@20m",
            "top_quartile_@20m",
        }:
            raise ValueError("checkpoints must contain one bottom and one top quartile row")

        anchors = [row.gold_deficit_at_15 for row in self.comeback_odds]
        if len(anchors) != 3:
            raise ValueError("comeback odds must contain exactly three anchors")
        if any(not math.isfinite(anchor) or anchor >= 0 for anchor in anchors):
            raise ValueError("comeback anchors must be finite, strictly negative integers")
        if len(set(anchors)) != len(anchors):
            raise ValueError("comeback anchors must be distinct")
        if any(left <= right for left, right in zip(anchors, anchors[1:])):
            raise ValueError("comeback anchors must be ordered mildest to most severe")
        return self
