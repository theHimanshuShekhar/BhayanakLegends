"""Improvement Journal + benchmark read endpoints over the local store."""

from __future__ import annotations

import json
import math
import re
import statistics
from typing import Any

from fastapi import APIRouter, HTTPException, Request

from .models import (
    BenchmarkResponse,
    Checkpoints,
    HabitOutcome,
    HistorySummary,
    PatchAggregate,
    PostGameDigest,
    RoleBenchmark,
    RoleBenchmarkPersonal,
    RoleBenchmarkPopulation,
    RoleRow,
    TrajectoryPoint,
)
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


def _eligible_rows(
    request: Request,
    *,
    patch: str | None,
    role: str | None,
    champion: str | None,
) -> list[dict[str, Any]]:
    return [
        row
        for row in request.app.state.store.all_matches()
        if row["patch"]
        and row["role"]
        and (patch is None or row["patch"] == patch)
        and (role is None or row["role"] == role.upper())
        and (champion is None or row["champion"] == champion)
    ]


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
    rows = request.app.state.store.all_matches()
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
    rows = request.app.state.store.all_matches()
    if not rows:
        return None
    latest = max(rows, key=lambda r: r["played_at"] or "")
    features = json.loads(latest["features_json"] or "{}")
    checkpoints = {
        f"gold_diff_{m}": features.get(f"gold_diff_{m}") for m in (10, 15, 20)
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
    ).model_dump()


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

    personal = _personal_medians(request.app.state.store.all_matches())
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
        features = json.loads(row["features_json"] or "{}")
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
    """Return only evaluated outcomes; no exact habit extractors exist in v1."""
    return []


def _headline(row: dict[str, Any]) -> str:
    outcome = "won" if row["win"] else "lost"
    minutes = int((row["duration_s"] or 0) // 60)
    champion = row["champion"] or "Unknown"
    return f"{outcome} as {champion} ({row['role'] or 'unknown role'}) in a {minutes}-minute game"
