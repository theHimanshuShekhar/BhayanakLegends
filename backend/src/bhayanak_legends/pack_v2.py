"""Typed Findings Pack v2 contract and semantic validation."""

from __future__ import annotations

import math
import re
from collections.abc import Mapping
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, FiniteFloat, StrictInt, model_validator

FindingTierV2 = Literal["actionable", "diagnostic", "a-lite"]
ReleaseStatusV2 = Literal["available", "approximate", "withheld", "superseded"]
EraStabilityV2 = Literal["stable", "sensitive", "insufficient", "not_evaluated"]
RoleV2 = Literal["TOP", "JUNGLE", "MIDDLE", "BOTTOM", "UTILITY"]
RankBandV2 = Literal["S", "A", "B", "C"]
ObjectiveV2 = Literal["dragon", "herald", "baron"]
ObjectiveMetricKindV2 = Literal[
    "possession_rate",
    "before_time_rate",
    "contested_first_rate",
    "no_objective_rate",
    "matched_effect",
]
FindingMetricKindV2 = Literal[
    "win_rate",
    "odds_ratio",
    "correlation",
    "percentage_points",
    "count",
    "auc",
    "status",
]
HabitMetricKindV2 = Literal[
    "odds_ratio_per_standard_deviation",
    "percentage_points",
    "win_rate",
]
BanMetricKindV2 = Literal["ban_rate_win_rate_correlation", "ban_rate", "win_rate"]
WindowKindV2 = Literal[
    "pooled",
    "full_match",
    "at_checkpoint",
    "before_time",
    "interval",
]
CoordinateValidationV2 = Literal["validated", "approximate", "unavailable"]

_SHA256 = re.compile(r"[0-9a-f]{64}")
_GENERATOR_REVISION = re.compile(r"sha256:[0-9a-f]{64}")


class PackV2Model(BaseModel):
    """Closed model base for v2; unknown fields are a contract failure."""

    model_config = ConfigDict(extra="forbid", strict=True)


class PackV2PatchRange(PackV2Model):
    min: str = Field(min_length=1)
    max: str = Field(min_length=1)

    @model_validator(mode="after")
    def ordered(self) -> "PackV2PatchRange":
        if _patch_key(self.min) > _patch_key(self.max):
            raise ValueError("patch_range min must not be newer than max")
        return self


class PackV2EvidenceMetadata(PackV2Model):
    patch_range: PackV2PatchRange
    population_scope: str = Field(min_length=1)
    era_stability: EraStabilityV2
    caveats: list[str] = Field(min_length=1)
    source_document: str = Field(min_length=1)
    source_section: str = Field(min_length=1)
    source_ref: str = Field(min_length=1)
    provenance_key: str = Field(min_length=1)

    @model_validator(mode="after")
    def nonempty_caveats(self) -> "PackV2EvidenceMetadata":
        if any(not isinstance(caveat, str) or not caveat.strip() for caveat in self.caveats):
            raise ValueError("v2 evidence caveats must be nonempty strings")
        return self


class PackV2Provenance(PackV2Model):
    source_document: str = Field(min_length=1)
    source_section: str = Field(min_length=1)
    source_ref: str = Field(min_length=1)
    feature_store_manifest_sha256: str
    generator_revision: str
    feature_contract_version: str = Field(min_length=1)

    @model_validator(mode="after")
    def hashes_are_canonical(self) -> "PackV2Provenance":
        if _SHA256.fullmatch(self.feature_store_manifest_sha256) is None:
            raise ValueError("feature_store_manifest_sha256 must be lowercase SHA-256 hex")
        if _GENERATOR_REVISION.fullmatch(self.generator_revision) is None:
            raise ValueError("generator_revision must be sha256:<64 lowercase hex>")
        return self


class PackV2Dataset(PackV2EvidenceMetadata):
    raw_unique_matches: StrictInt = Field(ge=0)
    eligible_matches: StrictInt = Field(ge=0)
    participant_performances: StrictInt = Field(ge=0)
    tracked_players: StrictInt = Field(ge=0)
    patch_buckets: StrictInt = Field(ge=0)
    median_game_minutes: FiniteFloat | None = Field(default=None, ge=0)
    surrender_rate: FiniteFloat | None = Field(default=None, ge=0, le=1)
    patches: list[str] = Field(min_length=1)
    eligibility: str = Field(min_length=1)

    @model_validator(mode="after")
    def patch_list_and_counts(self) -> "PackV2Dataset":
        if any(not isinstance(patch, str) or not patch for patch in self.patches):
            raise ValueError("dataset patches must contain nonempty strings")
        if self.eligible_matches > self.raw_unique_matches:
            raise ValueError("eligible matches cannot exceed raw unique matches")
        if self.patches != sorted(self.patches, key=_patch_key):
            raise ValueError("dataset patches must be deterministically ordered")
        if self.surrender_rate is not None and not math.isfinite(self.surrender_rate):
            raise ValueError("dataset surrender_rate must be finite when supplied")
        return self


class PackV2FeatureContracts(PackV2Model):
    population: str = Field(min_length=1)
    personal_history: str | None = None
    models: dict[str, str] | None = None

    @model_validator(mode="after")
    def model_versions_are_nonempty(self) -> "PackV2FeatureContracts":
        if self.models is not None and any(
            not isinstance(name, str) or not name or not isinstance(version, str) or not version
            for name, version in self.models.items()
        ):
            raise ValueError("model feature-contract versions must be nonempty strings")
        return self


class PackV2Finding(PackV2EvidenceMetadata):
    key: str = Field(min_length=1)
    tier: FindingTierV2
    release_status: ReleaseStatusV2
    title: str = Field(min_length=1)
    statement: str = Field(min_length=1)
    metric_kind: FindingMetricKindV2
    unit: str = Field(min_length=1)
    sample: StrictInt = Field(gt=0)
    value: object | None = None
    release_reason: str | None = None

    @model_validator(mode="before")
    @classmethod
    def forbid_unavailable_values(cls, value: object) -> object:
        if isinstance(value, Mapping):
            status = value.get("release_status")
            if status in {"withheld", "superseded"} and "value" in value:
                raise ValueError("withheld or superseded finding cannot carry a value")
        return value

    @model_validator(mode="after")
    def validate_release_and_value(self) -> "PackV2Finding":
        if self.release_status in {"withheld", "superseded"}:
            if not self.release_reason or not self.release_reason.strip():
                raise ValueError("withheld or superseded finding requires release_reason")
        elif self.release_reason is not None and not self.release_reason.strip():
            raise ValueError("release_reason must be nonempty when supplied")
        if self.metric_kind == "status" and self.value is not None and not isinstance(self.value, str):
            raise ValueError("status finding values must be status text")
        if self.metric_kind != "status" and self.value is not None:
            _validate_finite_json(self.value)
        return self


class PackV2Habit(PackV2EvidenceMetadata):
    key: str = Field(min_length=1)
    label: str = Field(min_length=1)
    metric_kind: HabitMetricKindV2
    unit: str = Field(min_length=1)
    effect: FiniteFloat
    feature: str = Field(min_length=1)
    eligibility: str = Field(min_length=1)
    tier: FindingTierV2
    release_status: ReleaseStatusV2
    sample: StrictInt = Field(gt=0)
    release_reason: str | None = None

    @model_validator(mode="after")
    def release_reason_for_unavailable(self) -> "PackV2Habit":
        if self.release_status in {"withheld", "superseded"} and not self.release_reason:
            raise ValueError("withheld or superseded habit requires release_reason")
        return self


class PackV2ObservationWindow(PackV2Model):
    kind: WindowKindV2
    start_seconds: FiniteFloat | None = Field(default=None, ge=0)
    end_seconds: FiniteFloat | None = Field(default=None, ge=0)
    include_start: bool
    include_end: bool
    rule: str = Field(min_length=1)

    @model_validator(mode="after")
    def bounds_are_possible(self) -> "PackV2ObservationWindow":
        if self.start_seconds is not None and self.end_seconds is not None:
            if self.end_seconds < self.start_seconds:
                raise ValueError("observation window end precedes start")
            if self.end_seconds == self.start_seconds and not (
                self.include_start and self.include_end
            ):
                raise ValueError("zero-width observation window must include both bounds")
        if self.kind in {"pooled", "full_match"} and (
            self.start_seconds is not None or self.end_seconds is not None
        ):
            raise ValueError("pooled/full_match window cannot carry checkpoint bounds")
        if self.kind == "before_time" and self.end_seconds is None:
            raise ValueError("before_time window requires end_seconds")
        if self.kind == "at_checkpoint":
            if self.start_seconds is None or self.end_seconds is None:
                raise ValueError("at_checkpoint window requires both bounds")
            if self.start_seconds != self.end_seconds:
                raise ValueError("at_checkpoint window must have equal bounds")
            if not (self.include_start and self.include_end):
                raise ValueError("at_checkpoint window includes its observation")
        if self.kind == "interval" and (
            self.start_seconds is None or self.end_seconds is None
        ):
            raise ValueError("interval window requires both bounds")
        return self


class PackV2Objective(PackV2EvidenceMetadata):
    objective: ObjectiveV2
    metric_kind: ObjectiveMetricKindV2
    window: PackV2ObservationWindow
    rate: FiniteFloat = Field(ge=0, le=1)
    sample: StrictInt = Field(gt=0)
    tier: FindingTierV2
    release_status: ReleaseStatusV2
    release_reason: str | None = None

    @model_validator(mode="after")
    def metric_window_semantics(self) -> "PackV2Objective":
        if self.metric_kind == "before_time_rate" and self.window.kind != "before_time":
            raise ValueError("before_time_rate requires a before_time observation window")
        if self.metric_kind == "contested_first_rate" and self.window.kind == "pooled":
            raise ValueError("contested_first_rate requires an observation window")
        if self.release_status in {"withheld", "superseded"} and not self.release_reason:
            raise ValueError("withheld or superseded objective requires release_reason")
        return self


class PackV2ComebackBand(PackV2EvidenceMetadata):
    feature: Literal["team_gold_diff_15m"]
    feature_contract_version: str = Field(min_length=1)
    checkpoint_seconds: Literal[900]
    unit: Literal["gold"]
    lower_bound: FiniteFloat = Field(ge=0)
    upper_bound: FiniteFloat | None = Field(default=None, ge=0)
    include_lower: bool
    include_upper: Literal[False]
    rate: FiniteFloat | None = Field(default=None, ge=0, le=1)
    sample: StrictInt = Field(ge=0)
    eligibility: str = Field(min_length=1)
    tier: FindingTierV2
    release_status: ReleaseStatusV2
    release_reason: str | None = None

    @model_validator(mode="after")
    def bounds_and_status(self) -> "PackV2ComebackBand":
        if self.upper_bound is not None and self.upper_bound <= self.lower_bound:
            raise ValueError("comeback upper bound must be greater than lower bound")
        if not self.include_lower:
            raise ValueError("comeback bands include their lower bound")
        if self.release_status == "available":
            if self.rate is None or self.sample <= 0:
                raise ValueError("available comeback bands require a rate and positive sample")
        elif self.rate is not None:
            raise ValueError("suppressed comeback bands must not carry a rate")
        if self.release_status in {"withheld", "superseded"} and not self.release_reason:
            raise ValueError("withheld or superseded comeback band requires release_reason")
        return self


class PackV2BanContext(PackV2EvidenceMetadata):
    key: str = Field(min_length=1)
    champion: str | None = None
    metric_kind: BanMetricKindV2
    value: FiniteFloat
    sample: StrictInt = Field(gt=0)
    tier: Literal["diagnostic"]
    release_status: ReleaseStatusV2
    release_reason: str | None = None

    @model_validator(mode="after")
    def pooled_correlation_has_no_champion(self) -> "PackV2BanContext":
        if self.metric_kind == "ban_rate_win_rate_correlation" and self.champion is not None:
            raise ValueError("pooled ban/win correlation must not carry a champion label")
        if self.release_status in {"withheld", "superseded"} and not self.release_reason:
            raise ValueError("withheld or superseded ban context requires release_reason")
        return self


class PackV2TierEntry(PackV2EvidenceMetadata):
    champion: str = Field(min_length=1)
    role: RoleV2
    games: StrictInt = Field(ge=0)
    observed_win_rate: FiniteFloat = Field(ge=0, le=1)
    role_pick_rate: FiniteFloat = Field(ge=0, le=1)
    rank_band: RankBandV2
    minimum_games: Literal[500]
    tier: Literal["diagnostic"]
    release_status: ReleaseStatusV2
    release_reason: str | None = None

    @model_validator(mode="after")
    def qualify_and_explain(self) -> "PackV2TierEntry":
        if self.games < self.minimum_games:
            raise ValueError("tier row does not meet the 500-game qualification floor")
        if self.release_status in {"withheld", "superseded"} and not self.release_reason:
            raise ValueError("withheld or superseded tier row requires release_reason")
        return self


class PackV2Interval(PackV2Model):
    lower: FiniteFloat
    upper: FiniteFloat
    include_lower: bool
    include_upper: bool

    @model_validator(mode="after")
    def ordered_and_bounded(self) -> "PackV2Interval":
        if not (0 <= self.lower <= self.upper <= 1):
            raise ValueError("matchup interval must be ordered and lie in [0,1]")
        if self.lower == self.upper and not (self.include_lower and self.include_upper):
            raise ValueError("zero-width matchup interval must include its endpoint")
        return self


class PackV2Matchup(PackV2EvidenceMetadata):
    champion: str = Field(min_length=1)
    opponent: str = Field(min_length=1)
    role: RoleV2
    games: StrictInt = Field(gt=0)
    estimate: FiniteFloat = Field(ge=0, le=1)
    interval: PackV2Interval
    tier: Literal["diagnostic"]
    release_status: ReleaseStatusV2
    release_reason: str | None = None

    @model_validator(mode="after")
    def no_self_and_release_reason(self) -> "PackV2Matchup":
        if self.champion == self.opponent:
            raise ValueError("self-matchup is not valid")
        if self.release_status in {"withheld", "superseded"} and not self.release_reason:
            raise ValueError("withheld or superseded matchup requires release_reason")
        if not self.interval.lower <= self.estimate <= self.interval.upper:
            raise ValueError("matchup estimate must lie inside its interval")
        return self


class PackV2Checkpoint(PackV2EvidenceMetadata):
    feature: str = Field(min_length=1)
    window: PackV2ObservationWindow
    value: FiniteFloat
    unit: str = Field(min_length=1)
    sample: StrictInt = Field(gt=0)
    tier: FindingTierV2
    release_status: ReleaseStatusV2
    release_reason: str | None = None


class PackV2RouteArchetype(PackV2EvidenceMetadata):
    key: str = Field(min_length=1)
    label: str = Field(min_length=1)
    sample: StrictInt = Field(gt=0)
    observed_outcome: FiniteFloat
    side_context: str | None
    champion_context: str | None
    coordinate_validation: CoordinateValidationV2
    tier: Literal["a-lite", "diagnostic"]
    release_status: Literal["approximate"]
    release_reason: str | None = None

    @model_validator(mode="after")
    def no_recommendation_language(self) -> "PackV2RouteArchetype":
        forbidden = ("best", "optimal", "recommend")
        text = f"{self.label} {' '.join(self.caveats)}".lower()
        if any(word in text for word in forbidden):
            raise ValueError("route archetypes cannot be presented as recommendations")
        return self


class PackV2BuildEvidence(PackV2EvidenceMetadata):
    release_status: Literal["withheld"]
    release_reason: str = Field(min_length=1)
    rows: list[object] | None = None

    @model_validator(mode="after")
    def no_withheld_rows(self) -> "PackV2BuildEvidence":
        if self.rows:
            raise ValueError("withheld build evidence cannot contain raw sequence rows")
        return self


class PackV2ModelInterval(PackV2Model):
    min: FiniteFloat
    max: FiniteFloat

    @model_validator(mode="after")
    def ordered(self) -> "PackV2ModelInterval":
        if self.min > self.max:
            raise ValueError("model domain minimum exceeds maximum")
        return self


class PackV2ModelFeature(PackV2Model):
    name: str = Field(min_length=1)
    dtype: Literal["float32"]
    unit: str = Field(min_length=1)
    source: str = Field(min_length=1)
    adjustable: bool
    bounds: PackV2ModelInterval


class PackV2PreprocessingStep(PackV2Model):
    name: str = Field(min_length=1)
    feature: str = Field(min_length=1)
    operation: str = Field(min_length=1)
    parameters: list[FiniteFloat] | None = None


class PackV2SmokeTest(PackV2Model):
    features: list[FiniteFloat] = Field(min_length=1)
    expected: FiniteFloat = Field(ge=0, le=1)
    tolerance: FiniteFloat = Field(ge=0)


class PackV2ModelValidation(PackV2Model):
    grouped_holdout: dict[str, FiniteFloat]
    temporal_holdout: dict[str, FiniteFloat]
    calibration: dict[str, FiniteFloat]
    parity: dict[str, str | int | float | bool]
    gates: dict[str, bool] | None = None


class PackV2ModelCard(PackV2Model):
    model_id: str = Field(min_length=1)
    model_version: str = Field(min_length=1)
    feature_contract_version: str = Field(min_length=1)
    input_names: list[str] = Field(min_length=1)
    output_names: list[str] = Field(min_length=1)
    features: list[PackV2ModelFeature] = Field(min_length=1)
    feature_order: list[str] = Field(min_length=1)
    preprocessing: list[PackV2PreprocessingStep]
    bounds: dict[str, PackV2ModelInterval]
    patch_scope: PackV2PatchRange
    validation: PackV2ModelValidation
    caveats: list[str] = Field(min_length=1)
    smoke_test: PackV2SmokeTest

    @model_validator(mode="after")
    def feature_contract_is_exact(self) -> "PackV2ModelCard":
        names = [feature.name for feature in self.features]
        if names != self.feature_order:
            raise ValueError("model feature_order must equal ordered feature declarations")
        if len(set(names)) != len(names):
            raise ValueError("model feature names must be unique")
        if any(name not in self.bounds for name in names):
            raise ValueError("model bounds must cover every ordered feature")
        if len(self.smoke_test.features) != len(names):
            raise ValueError("model smoke test must contain one value per feature")
        if any(not name for name in self.input_names + self.output_names):
            raise ValueError("model input/output names must be nonempty")
        if any(not isinstance(caveat, str) or not caveat.strip() for caveat in self.caveats):
            raise ValueError("model card caveats must be nonempty strings")
        return self


class PackV2Artifact(PackV2Model):
    path: str = Field(min_length=1)
    format: Literal["onnx"]
    sha256: str
    size: StrictInt = Field(gt=0)
    model_card_path: str = Field(min_length=1)

    @model_validator(mode="after")
    def hash_is_canonical(self) -> "PackV2Artifact":
        if _SHA256.fullmatch(self.sha256) is None:
            raise ValueError("model artifact sha256 must be lowercase SHA-256 hex")
        _safe_relative_path(self.path)
        _safe_relative_path(self.model_card_path)
        return self


class PackV2ModelDeclaration(PackV2Model):
    model_id: str = Field(min_length=1)
    release_status: ReleaseStatusV2
    artifact: PackV2Artifact | None = None
    model_card: PackV2ModelCard | None = None
    release_reason: str | None = None

    @model_validator(mode="after")
    def artifact_card_status(self) -> "PackV2ModelDeclaration":
        if self.release_status != "available":
            if self.artifact is not None or self.model_card is not None:
                raise ValueError("non-available models cannot carry executable declaration")
            if not self.release_reason:
                raise ValueError("suppressed models require release_reason")
        elif self.artifact is None or self.model_card is None:
            raise ValueError("available models require artifact and model card")
        elif self.model_card.model_id != self.model_id:
            raise ValueError("model declaration and card IDs differ")
        return self


class FindingsPackV2(PackV2Model):
    schema_version: Literal[2]
    pack_version: str = Field(min_length=1)
    generated_at: str = Field(min_length=1)
    patch_range: PackV2PatchRange
    dataset: PackV2Dataset
    feature_contracts: PackV2FeatureContracts
    provenance: dict[str, PackV2Provenance]
    findings: list[PackV2Finding]
    habits: list[PackV2Habit]
    objectives: list[PackV2Objective]
    comeback_odds: list[PackV2ComebackBand]
    ban_context: list[PackV2BanContext]
    tier_list: list[PackV2TierEntry]
    matchup_examples: list[PackV2Matchup]
    checkpoints: list[PackV2Checkpoint]
    route_archetypes: list[PackV2RouteArchetype]
    build_evidence: PackV2BuildEvidence
    models: dict[str, PackV2ModelDeclaration] | None = None

    @model_validator(mode="after")
    def validate_v2_contract(self) -> "FindingsPackV2":
        validate_pack_v2_semantics(self)
        return self


def _patch_key(value: str) -> tuple[int, ...]:
    try:
        return tuple(int(part) for part in value.split("."))
    except ValueError as exc:
        raise ValueError(f"invalid patch version {value!r}") from exc


def _validate_finite_json(value: object, *, path: str = "value") -> None:
    if isinstance(value, bool) or value is None:
        return
    if isinstance(value, (int, float)):
        if not math.isfinite(float(value)):
            raise ValueError(f"{path} must contain only finite numbers")
        return
    if isinstance(value, str):
        return
    if isinstance(value, list):
        for index, item in enumerate(value):
            _validate_finite_json(item, path=f"{path}[{index}]")
        return
    if isinstance(value, dict):
        for key, item in value.items():
            if not isinstance(key, str) or not key:
                raise ValueError(f"{path} object keys must be nonempty strings")
            _validate_finite_json(item, path=f"{path}.{key}")
        return
    raise ValueError(f"{path} contains an unsupported value")


def _safe_relative_path(value: str) -> None:
    if not value or value.startswith(("/", "\\")):
        raise ValueError("pack artifact paths must be relative")
    parts = value.replace("\\", "/").split("/")
    if any(part in {"", ".", ".."} for part in parts):
        raise ValueError("pack artifact path escapes its active directory")
    if ":" in parts[0]:
        raise ValueError("pack artifact path must not contain a drive")


def _within_patch_range(candidate: PackV2PatchRange, root: PackV2PatchRange) -> bool:
    return _patch_key(root.min) <= _patch_key(candidate.min) <= _patch_key(candidate.max) <= _patch_key(root.max)


TEAM_GOLD_FEATURE_CONTRACT_VERSION = "loltrends-parity-v2"


def _require_provenance(pack: FindingsPackV2) -> None:
    required = {
        "dataset",
        "findings",
        "habits",
        "objectives",
        "comeback_odds",
        "ban_context",
        "tier_list",
        "matchup_examples",
        "checkpoints",
        "route_archetypes",
        "build_evidence",
    }
    missing = sorted(required - set(pack.provenance))
    if missing:
        raise ValueError(f"v2 provenance missing required blocks: {', '.join(missing)}")
    declared_contracts = {
        value
        for value in (
            pack.feature_contracts.population,
            pack.feature_contracts.personal_history,
            *(pack.feature_contracts.models or {}).values(),
        )
        if value
    }
    for key, metadata in pack.provenance.items():
        if metadata.feature_contract_version not in declared_contracts:
            raise ValueError(f"provenance {key} uses an undeclared feature contract")

def _require_metadata_ranges(pack: FindingsPackV2) -> None:
    groups = (
        (pack.dataset,),
        tuple(pack.findings),
        tuple(pack.habits),
        tuple(pack.objectives),
        tuple(pack.comeback_odds),
        tuple(pack.ban_context),
        tuple(pack.tier_list),
        tuple(pack.matchup_examples),
        tuple(pack.checkpoints),
        tuple(pack.route_archetypes),
        (pack.build_evidence,),
    )
    for rows in groups:
        for row in rows:
            if not _within_patch_range(row.patch_range, pack.patch_range):
                raise ValueError("v2 evidence patch range lies outside pack patch range")
            provenance = pack.provenance.get(row.provenance_key)
            if provenance is None:
                raise ValueError(f"v2 evidence references unknown provenance key {row.provenance_key!r}")
            if row.source_document != provenance.source_document or row.source_section != provenance.source_section:
                raise ValueError("v2 evidence source does not match its provenance entry")
            if row.source_ref != provenance.source_ref:
                raise ValueError("v2 evidence source_ref does not match its provenance entry")

def _validate_comeback_bands(pack: FindingsPackV2) -> None:
    expected = ((2000, 3000), (3000, 5000), (5000, None))
    actual = tuple((row.lower_bound, row.upper_bound) for row in pack.comeback_odds)
    if actual != expected:
        raise ValueError("v2 comeback bands must be [2000,3000), [3000,5000), [5000,∞)")
    if any(
        row.feature_contract_version != TEAM_GOLD_FEATURE_CONTRACT_VERSION
        for row in pack.comeback_odds
    ):
        raise ValueError("comeback feature contract does not match team_gold_diff_15m contract")
    if any("team_gold_diff_15m" != row.feature for row in pack.comeback_odds):
        raise ValueError("v2 comeback bands must use team_gold_diff_15m")


def _validate_lists(pack: FindingsPackV2) -> None:
    if [row.key for row in pack.findings] != sorted(row.key for row in pack.findings):
        raise ValueError("v2 findings must be deterministically ordered by key")
    if len({row.key for row in pack.findings}) != len(pack.findings):
        raise ValueError("v2 finding keys must be unique")
    if len({(row.champion, row.opponent, row.role) for row in pack.matchup_examples}) != len(
        pack.matchup_examples
    ):
        raise ValueError("v2 matchup directions must be unique")
    if [row.key for row in pack.route_archetypes] != sorted(row.key for row in pack.route_archetypes):
        raise ValueError("v2 route archetypes must be deterministically ordered by key")
    surrender = next((row for row in pack.findings if row.key == "surrender_advisor"), None)
    if surrender is None or surrender.release_status != "withheld":
        raise ValueError("v2 Surrender Advisor must be explicitly withheld")
    if "baron_comeback_lift_pp" in {row.key for row in pack.findings}:
        raise ValueError("unsupported Baron comeback lift must be absent from v2")


def validate_pack_v2_semantics(pack: FindingsPackV2) -> None:
    """Validate cross-row v2 semantics after Pydantic shape validation."""

    _require_provenance(pack)
    _require_metadata_ranges(pack)
    _validate_comeback_bands(pack)
    _validate_lists(pack)
    for row in pack.ban_context:
        if row.tier != "diagnostic":
            raise ValueError("ban context is diagnostic only")
    for model in (pack.models or {}).values():
        if model.artifact is not None and model.artifact.format != "onnx":
            raise ValueError("only ONNX model artifacts are accepted")




__all__ = [
    "FindingsPackV2",
    "PackV2Artifact",
    "PackV2BanContext",
    "PackV2BuildEvidence",
    "PackV2Checkpoint",
    "PackV2ComebackBand",
    "PackV2Dataset",
    "PackV2EvidenceMetadata",
    "PackV2FeatureContracts",
    "PackV2Finding",
    "PackV2Habit",
    "PackV2Interval",
    "PackV2Matchup",
    "PackV2ModelCard",
    "PackV2ModelDeclaration",
    "PackV2ModelFeature",
    "PackV2Objective",
    "PackV2ObservationWindow",
    "PackV2PatchRange",
    "PackV2Provenance",
    "PackV2RouteArchetype",
    "PackV2TierEntry",
    "validate_pack_v2_semantics",
]

