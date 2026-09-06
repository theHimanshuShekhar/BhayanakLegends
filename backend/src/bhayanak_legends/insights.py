"""Deterministic Personal History aggregation for the Improvement Journal.

This module deliberately knows nothing about the Findings Pack or population
rows.  Callers pass the already owner-scoped persisted matches; aggregation is
pure and therefore cannot accidentally blend accounts or invent a comparison
for a missing sample.
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterable, Mapping
from typing import Any, Literal

Role = Literal["TOP", "JUNGLE", "MIDDLE", "BOTTOM", "UTILITY", "UNKNOWN"]
ProfileSampleStatus = Literal["insufficient", "review"]
WindowCompleteness = Literal["full", "partial", "unavailable"]

ROLE_ORDER: tuple[Role, ...] = (
    "TOP",
    "JUNGLE",
    "MIDDLE",
    "BOTTOM",
    "UTILITY",
    "UNKNOWN",
)
WINDOW_SIZE = 50
MIN_REVIEW_SAMPLE = 5


def _role(value: object) -> Role:
    if isinstance(value, str):
        candidate = value.strip().upper()
        if candidate in ROLE_ORDER:
            return candidate  # type: ignore[return-value]
    return "UNKNOWN"


def _champion(value: object) -> str:
    if isinstance(value, str):
        candidate = value.strip()
        if candidate:
            return candidate
    return "UNKNOWN"


def _win(value: object) -> bool:
    # SQLite stores this column as 0/1.  Keeping the coercion in one place
    # makes fixture rows and persisted rows follow the same rule.
    return bool(value)


def _played_at(value: object) -> str:
    return value if isinstance(value, str) else ""


def _match_id(value: object) -> str:
    return value if isinstance(value, str) else str(value or "")


def _match_sort_key(row: Mapping[str, Any]) -> tuple[str, str]:
    """Canonical Personal History ordering: played-at, then match id."""
    return (_played_at(row.get("played_at")), _match_id(row.get("match_id")))


def _profile_status(games: int) -> ProfileSampleStatus:
    return "review" if games >= MIN_REVIEW_SAMPLE else "insufficient"


def _role_sort_key(role: str) -> int:
    try:
        return ROLE_ORDER.index(role)  # type: ignore[arg-type]
    except ValueError:
        return len(ROLE_ORDER)


def _rate(wins: int, games: int) -> float:
    return wins / games if games else 0.0


def _window(name: Literal["latest", "preceding"], rows: list[Mapping[str, Any]]) -> dict[str, Any]:
    games = len(rows)
    wins = sum(1 for row in rows if _win(row.get("win")))
    if games == 0:
        completeness: WindowCompleteness = "unavailable"
    elif games == WINDOW_SIZE:
        completeness = "full"
    else:
        completeness = "partial"
    return {
        "name": name,
        "games": games,
        "wins": wins,
        "win_rate": _rate(wins, games),
        "sample_status": _profile_status(games),
        "completeness": completeness,
    }


def _normalise_filter_role(value: str | None) -> str | None:
    if value is None:
        return None
    candidate = value.strip().upper()
    return candidate if candidate in ROLE_ORDER else "__NO_MATCH__"
def _feature_contract_state(rows: Iterable[Mapping[str, Any]]) -> tuple[str | None, str]:
    versions: set[str] = set()
    for row in rows:
        version = row.get("feature_contract_version")
        if isinstance(version, str) and version.strip():
            versions.add(version.strip())
            continue
        features = row.get("features")
        if isinstance(features, Mapping):
            nested = features.get("feature_contract_version")
            if isinstance(nested, str) and nested.strip():
                versions.add(nested.strip())
    if not versions:
        return None, "unavailable"
    if len(versions) == 1:
        return next(iter(versions)), "available"
    return None, "mixed"



def aggregate_insights(
    rows: Iterable[Mapping[str, Any]],
    *,
    role: str | None = None,
    champion: str | None = None,
) -> dict[str, Any]:
    """Aggregate one already owner-scoped Personal History collection.

    Filters are applied before any profile grouping or review-window slicing.
    Rows with missing or unrecognised roles remain visible in the explicit
    ``UNKNOWN`` bucket.  The latest window is the final 50 rows in canonical
    order; the preceding window is the 50 rows immediately before it, or an
    honest partial/unavailable window when the filtered history is shorter.
    """
    role_filter = _normalise_filter_role(role)
    champion_filter = champion.strip() if isinstance(champion, str) else None
    if champion_filter == "":
        champion_filter = None

    filtered: list[Mapping[str, Any]] = []
    for row in rows:
        row_role = _role(row.get("role"))
        row_champion = _champion(row.get("champion"))
        if role_filter is not None and row_role != role_filter:
            continue
        if champion_filter is not None and row_champion != champion_filter:
            continue
        filtered.append(row)

    ordered = sorted(filtered, key=_match_sort_key)

    role_counts: dict[Role, tuple[int, int]] = defaultdict(lambda: (0, 0))
    champion_counts: dict[str, tuple[int, int]] = defaultdict(lambda: (0, 0))
    champion_roles: dict[str, set[Role]] = defaultdict(set)
    feature_contract_version, feature_contract_status = _feature_contract_state(ordered)
    for row in ordered:
        row_role = _role(row.get("role"))
        row_champion = _champion(row.get("champion"))
        games, wins = role_counts[row_role]
        role_counts[row_role] = (games + 1, wins + int(_win(row.get("win"))))
        games, wins = champion_counts[row_champion]
        champion_counts[row_champion] = (games + 1, wins + int(_win(row.get("win"))))
        champion_roles[row_champion].add(row_role)

    roles = []
    for row_role in sorted(role_counts, key=_role_sort_key):
        games, wins = role_counts[row_role]
        roles.append(
            {
                "role": row_role,
                "games": games,
                "wins": wins,
                "win_rate": _rate(wins, games),
                "sample_status": _profile_status(games),
            }
        )

    champions = []
    for champion_name in sorted(
        champion_counts,
        key=lambda value: (-champion_counts[value][0], -champion_counts[value][1], value.casefold(), value),
    ):
        games, wins = champion_counts[champion_name]
        champions.append(
            {
                "champion": champion_name,
                "games": games,
                "wins": wins,
                "win_rate": _rate(wins, games),
                "roles": sorted(champion_roles[champion_name], key=_role_sort_key),
                "sample_status": _profile_status(games),
            }
        )

    if len(ordered) <= WINDOW_SIZE:
        latest_rows = ordered
        preceding_rows: list[Mapping[str, Any]] = []
    else:
        latest_rows = ordered[-WINDOW_SIZE:]
        preceding_rows = ordered[max(0, len(ordered) - (WINDOW_SIZE * 2)) : -WINDOW_SIZE]
    return {
        "state": "available" if ordered else "empty",
        "sample_size": len(ordered),
        "filters": {
            "role": role_filter if role_filter in ROLE_ORDER else None,
            "champion": champion_filter,
        },
        "feature_contract_version": feature_contract_version,
        "feature_contract_status": feature_contract_status,
        "roles": roles,
        "champions": champions,
        "windows": {
            "latest": _window("latest", latest_rows),
            "preceding": _window("preceding", preceding_rows),
        },
    }
