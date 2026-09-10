"""Improvement Journal + benchmark read endpoints over the local store."""

from __future__ import annotations

import json
import math
import re
import statistics
from collections.abc import Mapping
from typing import Any

from fastapi import APIRouter, HTTPException, Request

from .models import (
    BenchmarkResponse,
    Checkpoints,
    HabitOutcome,
    HistoryInsights,
    HistorySummary,
    PatchAggregate,
    PostGameDigest,
    RoleBenchmark,
    RoleBenchmarkPersonal,
    RoleBenchmarkPopulation,
    RoleRow,
    TeamState,
    TrajectoryPoint,
    WhatIfRequest,
    WhatIfResponse,
)
from .extract_v2 import PARITY_V2_VERSION
from .insights import aggregate_insights
from .pack import PackError

BENCHMARK_FIELD_CONTRACT = (
    {
        "canonical_name": "cs10",
        "unit": "minions",
        "population_feature": "cs10",
        "personal_extractor": "cs10",
        "population_column": "cs10_median",
        "eligible_roles": frozenset({"TOP", "JUNGLE", "MIDDLE", "BOTTOM", "UTILITY"}),
        "missing_data_rule": "omit the comparison when either side is missing",
        "source_ref": "docs/CONTRACT.md#benchmark-feature-contract",
    },
    {
        "canonical_name": "level10",
        "unit": "levels",
        "population_feature": "level10",
        "personal_extractor": "level10",
        "population_column": "level10_median",
        "eligible_roles": frozenset({"TOP", "JUNGLE", "MIDDLE", "BOTTOM", "UTILITY"}),
        "missing_data_rule": "omit the comparison when either side is missing",
        "source_ref": "docs/CONTRACT.md#benchmark-feature-contract",
    },
    {
        "canonical_name": "gold_diff_10",
        "unit": "gold",
        "population_feature": "gold_diff_10",
        "personal_extractor": "gold_diff_10",
        "population_column": "gold_diff_10_median",
        "eligible_roles": frozenset({"TOP", "JUNGLE", "MIDDLE", "BOTTOM", "UTILITY"}),
        "missing_data_rule": "omit the comparison when either side is missing",
        "source_ref": "docs/CONTRACT.md#benchmark-feature-contract",
    },
)


def _finite_number(value: object) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(float(value))

router = APIRouter()

ROLLING_WINDOW = 10
_PATCH_RE = re.compile(r"^(\d+)\.(\d+)$")


def _patch_sort_key(patch: str | None) -> tuple[int, int, int, str]:
    """Order valid numeric patches first; malformed values sort last by text.

    Missing patches are omitted by the summary and trajectory filters because
    there is no patch range to render, making omission the deterministic fallback.
    """
    if not patch:
        return (1, 0, 0, "")
    match = _PATCH_RE.fullmatch(patch)
    if match:
        return (0, int(match.group(1)), int(match.group(2)), patch)
    return (1, 0, 0, patch)


def _owner_rows(request: Request) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    """Capture owner once; unresolved transitions never fall back to old rows."""
    scope = request.app.state.store.capture_owner_scope()
    owner_key = scope.get("read_owner_key")
    if not owner_key:
        return scope, []
    return scope, request.app.state.store.all_matches(owner_key=owner_key)


def _eligible_rows(
    request: Request,
    *,
    patch: str | None,
    role: str | None,
    champion: str | None,
) -> list[dict[str, Any]]:
    _scope, rows = _owner_rows(request)
    return [
        row
        for row in rows
        if row["patch"]
        and row["role"]
        and (patch is None or row["patch"] == patch)
        and (role is None or row["role"] == role.upper())
        and (champion is None or row["champion"] == champion)
    ]
def _decode_features(row: Mapping[str, Any]) -> dict[str, Any]:
    try:
        decoded = json.loads(row.get("features_json") or "{}")
    except (TypeError, ValueError, json.JSONDecodeError):
        return {}
    return decoded if isinstance(decoded, dict) else {}


def _v2_features(raw_features: Mapping[str, Any]) -> dict[str, Any]:
    """Return only the nested features declared by the v2 contract."""
    if raw_features.get("feature_contract_version") != PARITY_V2_VERSION:
        return {}
    features = raw_features.get("features")
    return features if isinstance(features, dict) else {}

def _latest_row(rows: list[dict[str, Any]]) -> dict[str, Any] | None:
    return max(rows, key=lambda row: (row.get("played_at") or "", row.get("match_id") or "")) if rows else None



def _match_sort_key(row: dict[str, Any]) -> tuple[str, str]:
    return (row["played_at"] or "", row["match_id"])


@router.get("/progress/aggregates", response_model=list[PatchAggregate])
def patch_aggregates(
    request: Request,
    patch: str | None = None,
    role: str | None = None,
    champion: str | None = None,
) -> list[dict]:
    rows = _eligible_rows(request, patch=patch, role=role, champion=champion)
    grouped: dict[str, tuple[int, int]] = {}
    for row in rows:
        games, wins = grouped.get(row["patch"], (0, 0))
        grouped[row["patch"]] = (games + 1, wins + int(row["win"]))

    return [
        PatchAggregate(
            patch=patch_name,
            games=games,
            wins=wins,
            win_rate=wins / games if games else 0.0,
        ).model_dump()
        for patch_name, (games, wins) in sorted(
            grouped.items(), key=lambda item: _patch_sort_key(item[0])
        )
    ]


@router.get("/history/summary", response_model=HistorySummary)
def history_summary(request: Request) -> HistorySummary:
    _scope, rows = _owner_rows(request)
    games = len(rows)
    wins = sum(1 for r in rows if r["win"])
    patches = sorted({r["patch"] for r in rows if r["patch"]}, key=_patch_sort_key)
    by_role: dict[str, RoleRow] = {}
    for row in rows:
        role = row["role"]
        if not role:
            continue
        entry = by_role.setdefault(role, RoleRow(role=role, games=0, wins=0))
        entry.games += 1
        if row["win"]:
            entry.wins += 1
    return {
        "matches": games,
        "patches": patches,
        "by_role": [entry.model_dump() for entry in sorted(by_role.values(), key=lambda e: e.role)],
        "win_rate": (wins / games) if games else 0.0,
    }


@router.get("/history/insights", response_model=HistoryInsights)
def history_insights(
    request: Request,
    role: str | None = None,
    champion: str | None = None,
) -> dict:
    _scope, rows = _owner_rows(request)
    return aggregate_insights(rows, role=role, champion=champion)


@router.get("/progress/trajectories", response_model=list[TrajectoryPoint])
def trajectories(
    request: Request,
    patch: str | None = None,
    role: str | None = None,
    champion: str | None = None,
) -> list[dict]:
    ordered = sorted(
        _eligible_rows(request, patch=patch, role=role, champion=champion),
        key=_match_sort_key,
    )

    points: list[dict] = []
    for index, row in enumerate(ordered):
        window = ordered[max(0, index - ROLLING_WINDOW + 1) : index + 1]
        wins = sum(1 for match in window if match["win"])
        points.append(
            TrajectoryPoint(
                patch=row["patch"],
                role=row["role"],
                champion=row["champion"],
                played_at=row["played_at"] or "",
                index=index,
                rolling_wr=(wins / len(window)) if window else 0.0,
            ).model_dump()
        )
    return points
@router.get("/postgame/latest", response_model=PostGameDigest | None)
def postgame_latest(request: Request) -> dict | None:
    _scope, rows = _owner_rows(request)
    latest = _latest_row(rows)
    if latest is None:
        return None
    raw_features = _decode_features(latest)
    raw_contract = raw_features.get("feature_contract_version")
    feature_contract_version = (
        raw_contract if raw_contract == PARITY_V2_VERSION else None
    )
    eligibility = raw_features.get("personal_history_eligibility")
    if eligibility not in {"eligible", "ineligible", "unknown"}:
        eligibility = "unknown"
    candidate_features = _v2_features(raw_features)
    numeric_features = {
        key: float(value)
        for key, value in candidate_features.items()
        if _finite_number(value)
    }
    team_state = raw_features.get("team_state")
    try:
        parsed_team_state = (
            TeamState.model_validate(team_state)
            if feature_contract_version is not None and isinstance(team_state, dict)
            else None
        )
    except ValueError:
        parsed_team_state = None
    if parsed_team_state is None:
        # A flat team feature is not a substitute for the required nested
        # TeamState declaration.  Keep unrelated v2 fields, but suppress the
        # team comparison when its declaration is absent or malformed.
        numeric_features.pop("team_gold_diff_15m", None)
    else:
        flat_team_value = numeric_features.get("team_gold_diff_15m")
        nested_team_value = parsed_team_state.team_gold_diff_15m
        if (
            flat_team_value is None
            or nested_team_value is None
            or flat_team_value != nested_team_value
        ):
            numeric_features.pop("team_gold_diff_15m", None)
            parsed_team_state = None
    checkpoints = {
        "gold_diff_10": numeric_features.get("gold_diff_10"),
        "gold_diff_15": None,
        "gold_diff_20": None,
    }
    return PostGameDigest(
        match_id=latest["match_id"],
        played_at=latest["played_at"] or "",
        champion=latest["champion"] or "Unknown",
        role=latest["role"] or "UNKNOWN",
        win=bool(latest["win"]),
        duration_s=int(latest["duration_s"] or 0),
        checkpoints=Checkpoints.model_validate(checkpoints),
        habits=_habit_outcomes(request),
        headline=_headline(latest),
        feature_contract_version=feature_contract_version,
        personal_history_eligibility=eligibility,
        features=numeric_features,
        team_state=parsed_team_state,
    ).model_dump(exclude_none=True)

@router.post("/history/what-if", response_model=WhatIfResponse)
def history_what_if(request: Request, body: WhatIfRequest) -> dict:
    _scope, rows = _owner_rows(request)
    latest = _latest_row(rows)
    runtime = getattr(request.app.state, "inference_runtime", None)
    if latest is None or runtime is None:
        return WhatIfResponse(
            status="suppressed",
            reason="compatible Personal History or model runtime is unavailable",
        ).model_dump()
    features = _decode_features(latest)
    personal_features = _v2_features(features)
    result = runtime.what_if_from_personal_features(
        body.adjustments,
        personal_features,
        patch=latest.get("patch"),
    )
    return result.model_dump(exclude_none=True)


@router.get(
    "/benchmarks",
    response_model=BenchmarkResponse,
    response_model_exclude_none=True,
)
def benchmarks(request: Request) -> dict:
    try:
        pack = request.app.state.pack.load()
    except PackError:
        raise HTTPException(status_code=503, detail="Findings Pack validation failed") from None

    _scope, rows = _owner_rows(request)
    personal = _personal_medians(rows)
    compatible_cells = 0
    result: list[dict] = []
    for entry in pack.get("benchmarks", []):
        role = str(entry.get("role"))
        mine = personal.get(role, {})
        feature_contract = entry.get("feature_contract")
        if not isinstance(feature_contract, dict):
            continue
        personal_values: dict[str, float] = {}
        population_values: dict[str, float | int] = {}
        for definition in BENCHMARK_FIELD_CONTRACT:
            if role not in definition["eligible_roles"]:
                continue
            if definition["population_feature"] != definition["personal_extractor"]:
                continue
            population_column = definition["population_column"]
            if feature_contract.get(population_column) != definition["population_feature"]:
                continue
            population_value = entry.get(population_column)
            if not _finite_number(population_value):
                continue
            compatible_cells += 1
            personal_value = mine.get(definition["canonical_name"])
            if not _finite_number(personal_value):
                continue
            personal_values[definition["canonical_name"]] = float(personal_value)
            population_values[population_column] = float(population_value)
        if not personal_values:
            continue
        population_values["sample"] = entry.get("sample", 0)
        result.append(
            RoleBenchmark(
                role=role,
                personal=RoleBenchmarkPersonal.model_validate(personal_values),
                population=RoleBenchmarkPopulation.model_validate(population_values),
            ).model_dump(exclude_none=True)
        )
    state = (
        "available"
        if result
        else "insufficient-personal-history"
        if compatible_cells
        else "contract-suppressed"
    )
    return BenchmarkResponse(state=state, rows=result).model_dump(exclude_none=True)


def _personal_medians(rows: list[dict[str, Any]]) -> dict[str, dict[str, float]]:
    per_role: dict[str, dict[str, list[float]]] = {}
    for row in rows:
        role = row["role"]
        if not role:
            continue
        features = _v2_features(_decode_features(row))
        bucket = per_role.setdefault(
            role,
            {definition["canonical_name"]: [] for definition in BENCHMARK_FIELD_CONTRACT},
        )
        for definition in BENCHMARK_FIELD_CONTRACT:
            value = features.get(definition["personal_extractor"])
            if _finite_number(value):
                bucket[definition["canonical_name"]].append(float(value))
    medians: dict[str, dict[str, float]] = {}
    for role, bucket in per_role.items():
        medians[role] = {
            key: statistics.median(values) for key, values in bucket.items() if values
        }
    return medians

def _habit_outcomes(_request: Request) -> list[HabitOutcome]:
    """Return only evaluated outcomes; no exact habit extractors exist in v2."""
    return []


def _headline(row: dict[str, Any]) -> str:
    outcome = "won" if row["win"] else "lost"
    minutes = int((row["duration_s"] or 0) // 60)
    champion = row["champion"] or "Unknown"
    return f"{outcome} as {champion} ({row['role'] or 'unknown role'}) in a {minutes}-minute game"
