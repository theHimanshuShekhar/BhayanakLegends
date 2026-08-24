"""Improvement Journal + benchmark read endpoints over the local store."""

from __future__ import annotations

import json
import re
import statistics
from typing import Any

from fastapi import APIRouter, Request

from .models import HabitOutcome, PostGameDigest, RoleBenchmark, RoleRow, TrajectoryPoint
from .pack import PackError

router = APIRouter()

HABIT_KEYS = ("recall_safety", "fast_first_dragon", "spend_before_backing", "plates_by_14")
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


def _patch_group_sort_key(key: tuple[str, str, str | None]) -> tuple:
    return (_patch_sort_key(key[0]), key[1], key[2] or "")


@router.get("/history/summary")
def history_summary(request: Request) -> dict:
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


@router.get("/progress/trajectories")
def trajectories(
    request: Request,
    patch: str | None = None,
    role: str | None = None,
    champion: str | None = None,
) -> list[dict]:
    rows = [
        row
        for row in request.app.state.store.all_matches()
        if row["patch"] and row["role"]
        and (patch is None or row["patch"] == patch)
        and (role is None or row["role"] == role.upper())
        and (champion is None or row["champion"] == champion)
    ]
    groups: dict[tuple[str, str, str | None], list[dict[str, Any]]] = {}
    for row in rows:
        key = (row["patch"], row["role"], row["champion"])
        groups.setdefault(key, []).append(row)

    points: list[dict] = []
    for key in sorted(groups, key=_patch_group_sort_key):
        ordered = sorted(groups[key], key=lambda r: r["played_at"] or "")
        for index in range(len(ordered)):
            window = ordered[max(0, index - ROLLING_WINDOW + 1) : index + 1]
            wins = sum(1 for r in window if r["win"])
            points.append(
                TrajectoryPoint(
                    patch=key[0],
                    role=key[1],
                    champion=key[2],
                    games=len(window),
                    wins=wins,
                    rolling_wr=(wins / len(window)) if window else 0.0,
                ).model_dump()
            )
    return points


@router.get("/postgame/latest")
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
        checkpoints=checkpoints,
        habits=_habit_outcomes(request),
        headline=_headline(latest),
    ).model_dump()


@router.get("/benchmarks")
def benchmarks(request: Request) -> list[dict]:
    try:
        pack = request.app.state.pack.load()
    except PackError:
        return []
    personal = _personal_medians(request.app.state.store.all_matches())
    result: list[dict] = []
    for entry in pack.get("benchmarks", []):
        role = str(entry.get("role"))
        mine = personal.get(role, {})
        result.append(
            RoleBenchmark(
                role=role,
                personal={
                    "cs10": mine.get("cs10"),
                    "level10": mine.get("level10"),
                    "gold10": mine.get("gold10"),
                },
                population={
                    "cs10_median": entry.get("cs10_median"),
                    "level10_median": entry.get("level10_median"),
                    "gold10_median": entry.get("gold10_median"),
                    "sample": entry.get("sample", 0),
                },
            ).model_dump()
        )
    return result


def _personal_medians(rows: list[dict[str, Any]]) -> dict[str, dict[str, float]]:
    per_role: dict[str, dict[str, list[float]]] = {}
    for row in rows:
        role = row["role"]
        if not role:
            continue
        features = json.loads(row["features_json"] or "{}")
        bucket = per_role.setdefault(role, {"cs10": [], "level10": [], "gold10": []})
        for key, source in (("cs10", "cs10"), ("level10", "level10"), ("gold10", "gold_diff_10")):
            value = features.get(source)
            if isinstance(value, (int, float)):
                bucket[key].append(float(value))
    medians: dict[str, dict[str, float]] = {}
    for role, bucket in per_role.items():
        medians[role] = {
            key: statistics.median(values) for key, values in bucket.items() if values
        }
    return medians


def _habit_outcomes(request: Request) -> list[HabitOutcome]:
    labels: dict[str, str] = {}
    try:
        pack = request.app.state.pack.load()
        labels = {h["key"]: h.get("label", h["key"]) for h in pack.get("habits", [])}
    except PackError:
        pass
    return [
        HabitOutcome(
            key=key,
            label=labels.get(key, key.replace("_", " ").capitalize()),
            value="n/a",
            verdict="n/a",
        )
        for key in HABIT_KEYS
    ]


def _headline(row: dict[str, Any]) -> str:
    outcome = "won" if row["win"] else "lost"
    minutes = int((row["duration_s"] or 0) // 60)
    champion = row["champion"] or "Unknown"
    return f"{outcome} as {champion} ({row['role'] or 'unknown role'}) in a {minutes}-minute game"
