"""Historical Findings Pack v1 model and semantic contract.

Pack v1 is intentionally isolated from the v2 contract.  It remains readable
for already-installed bundles so unrelated evidence (tier lists, benchmarks,
and findings) does not disappear during the v2 cutover.  Its comeback anchors
and personal checkpoint names are historical values; callers must not translate
them into the v2 team-state contract.
"""

from __future__ import annotations

import math
from math import isfinite
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, FiniteFloat, StrictInt, model_validator


FindingTierV1 = Literal["actionable", "diagnostic", "a-lite"]
RoleV1 = Literal["TOP", "JUNGLE", "MIDDLE", "BOTTOM", "UTILITY", "UNKNOWN"]


class PackV1Model(BaseModel):
    """Historical v1 models intentionally ignore future v1-only fields."""

    model_config = ConfigDict(extra="ignore")


class PackV1TableProvenance(PackV1Model):
    source_document: str = Field(min_length=1)
    source_section: str = Field(min_length=1)
    feature_store_manifest_sha256: str = Field(min_length=1)
    generator_revision: str = Field(min_length=1)
    feature_contract_version: Literal["loltrends-parity-v1"]


class PackV1ComebackFeatureContract(PackV1Model):
    feature: str = Field(min_length=1)
    feature_contract_version: str = Field(min_length=1)

    def is_compatible(self) -> bool:
        return (
            self.feature == "gold_diff_15"
            and self.feature_contract_version == "loltrends-parity-v1"
        )


class PackV1Provenance(PackV1Model):
    dataset: PackV1TableProvenance
    findings: PackV1TableProvenance
    habits: PackV1TableProvenance
    objectives: PackV1TableProvenance
    comeback_odds: PackV1TableProvenance
    ban_advisor: PackV1TableProvenance
    trap_picks: PackV1TableProvenance
    tier_list: PackV1TableProvenance
    matchup_examples: PackV1TableProvenance
    benchmarks: PackV1TableProvenance
    checkpoints: PackV1TableProvenance


class PackV1Finding(PackV1Model):
    key: str = Field(min_length=1)
    tier: FindingTierV1
    title: str = Field(min_length=1)
    statement: str = Field(min_length=1)
    value: float | None = None
    unit: str | None = None
    source_ref: str = Field(min_length=1)


class PackV1Habit(PackV1Model):
    key: str = Field(min_length=1)
    label: str = Field(min_length=1)
    effect_per_sd: FiniteFloat


class PackV1BanAdvice(PackV1Model):
    champion: str = Field(min_length=1)
    win_rate: FiniteFloat = Field(ge=0, le=1)
    ban_rate: FiniteFloat = Field(ge=0, le=1)
    recommendation: Literal["real-threat", "fear-ban", "skip"]


class PackV1TrapPick(PackV1Model):
    champion: str = Field(min_length=1)
    win_rate: FiniteFloat = Field(ge=0, le=1)


class PackV1TierEntry(PackV1Model):
    champion: str = Field(min_length=1)
    role: RoleV1
    games: StrictInt = Field(ge=0)
    pick_rate: FiniteFloat = Field(ge=0, le=1)
    win_rate: FiniteFloat = Field(ge=0, le=1)
    tier: Literal["S", "A", "B", "C"]


class PackV1MatchupExample(PackV1Model):
    champion: str = Field(min_length=1)
    opponent: str = Field(min_length=1)
    role: RoleV1
    wr: FiniteFloat = Field(ge=0, le=1)
    ci: FiniteFloat = Field(ge=0)
    games: StrictInt = Field(ge=0)


class PackV1FeatureContract(PackV1Model):
    cs10_median: Literal["cs10", "lane_minions_first_10m"] | None = None
    level10_median: Literal["level10"] | None = None
    gold_diff_10_median: Literal["gold_diff_10"] | None = None

    @model_validator(mode="after")
    def require_declaration(self) -> "PackV1FeatureContract":
        if not any((self.cs10_median, self.level10_median, self.gold_diff_10_median)):
            raise ValueError("feature_contract must declare at least one benchmark feature")
        return self


class PackV1Benchmark(PackV1Model):
    role: RoleV1
    cs10_median: FiniteFloat | None = None
    level10_median: FiniteFloat | None = None
    gold_diff_10_median: FiniteFloat | None = None
    feature_contract: PackV1FeatureContract
    sample: StrictInt = Field(gt=0)

    @model_validator(mode="before")
    @classmethod
    def reject_explicit_nulls(cls, value: object) -> object:
        if isinstance(value, dict):
            for field in ("cs10_median", "level10_median", "gold_diff_10_median"):
                if field in value and value[field] is None:
                    raise ValueError(f"{field} must be omitted when unavailable")
        return value

    @model_validator(mode="after")
    def require_matching_declarations(self) -> "PackV1Benchmark":
        for field in ("cs10_median", "level10_median", "gold_diff_10_median"):
            median = getattr(self, field)
            declaration = getattr(self.feature_contract, field)
            if (median is None) != (declaration is None):
                raise ValueError(f"{field} median and declaration must be paired")
            if median is not None and not isfinite(median):
                raise ValueError(f"{field} median must be finite")
        return self


class PackV1Dataset(PackV1Model):
    matches: StrictInt = Field(ge=0)
    player_games: StrictInt = Field(ge=0)
    patches: list[str]


class PackV1ComebackOdds(PackV1Model):
    gold_deficit_at_15: StrictInt
    win_rate: FiniteFloat = Field(ge=0, le=1)


class PackV1Checkpoint(PackV1Model):
    gold_diff_bucket: Literal["bottom_quartile_@20m", "top_quartile_@20m"]
    win_rate: FiniteFloat = Field(ge=0, le=1)


class FindingsPackV1(PackV1Model):
    schema_version: Literal[1]
    pack_version: str = Field(default="v1", min_length=1)
    generated_at: str = Field(min_length=1)
    comeback_feature_contract: PackV1ComebackFeatureContract
    provenance: PackV1Provenance
    dataset: PackV1Dataset
    findings: list[PackV1Finding]
    habits: list[PackV1Habit]
    objectives: dict[str, FiniteFloat]
    comeback_odds: list[PackV1ComebackOdds]
    ban_advisor: list[PackV1BanAdvice]
    trap_picks: list[PackV1TrapPick]
    tier_list: list[PackV1TierEntry]
    matchup_examples: list[PackV1MatchupExample]
    benchmarks: list[PackV1Benchmark]
    checkpoints: list[PackV1Checkpoint]

    @model_validator(mode="after")
    def validate_pack_contract(self) -> "FindingsPackV1":
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


def build_v1_schema() -> dict[str, Any]:
    """Return the dedicated historical schema used for explicit v1 dispatch."""

    schema = FindingsPackV1.model_json_schema()
    schema["$schema"] = "https://json-schema.org/draft/2020-12/schema"
    return schema


__all__ = [
    "FindingsPackV1",
    "PackV1BanAdvice",
    "PackV1Benchmark",
    "PackV1Checkpoint",
    "PackV1ComebackFeatureContract",
    "PackV1ComebackOdds",
    "PackV1Dataset",
    "PackV1FeatureContract",
    "PackV1Finding",
    "PackV1Habit",
    "PackV1MatchupExample",
    "PackV1Provenance",
    "PackV1TableProvenance",
    "PackV1TierEntry",
    "PackV1TrapPick",
    "build_v1_schema",
]
