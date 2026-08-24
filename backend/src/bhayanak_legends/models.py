"""Pydantic models mirroring docs/CONTRACT.md. Frontend types live in src/api/types.ts."""

from pydantic import BaseModel


class Health(BaseModel):
    status: str = "ok"
    app_version: str
    pack_version: str | None = None


class Settings(BaseModel):
    riot_id: str | None = None
    region_route: str = "sea"
    has_key: bool = False
    auto_sync: bool = False


class SettingsPatch(BaseModel):
    riot_id: str | None = None
    region_route: str | None = None
    riot_key: str | None = None
    auto_sync: bool | None = None


class SyncStatus(BaseModel):
    state: str = "idle"
    mode: str = "era_first"
    total_queued: int = 0
    downloaded: int = 0
    skipped: int = 0
    failed: int = 0
    current_match_id: str | None = None
    started_at: str | None = None


class RoleRow(BaseModel):
    role: str
    games: int
    wins: int


class HistorySummary(BaseModel):
    matches: int
    patches: list[str]
    by_role: list[RoleRow]
    win_rate: float


class TrajectoryPoint(BaseModel):
    patch: str
    role: str
    champion: str | None = None
    games: int
    wins: int
    rolling_wr: float


class HabitOutcome(BaseModel):
    key: str
    label: str
    value: str
    verdict: str


class PostGameDigest(BaseModel):
    match_id: str
    played_at: str
    champion: str
    role: str
    win: bool
    duration_s: int
    checkpoints: dict[str, float | None]
    habits: list[HabitOutcome]
    headline: str


class RoleBenchmark(BaseModel):
    role: str
    personal: dict[str, float | None]
    population: dict[str, float | int | None]


class LiveState(BaseModel):
    active: bool = False
    phase: str | None = None
    game_id: int | None = None
    mode: str | None = None
    clock_s: int = 0


class LiveStatus(BaseModel):
    champ_select: LiveState
    ingame: LiveState
    last_error: str | None = None
