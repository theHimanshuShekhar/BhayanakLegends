"""Deterministic Personal History aggregation for the Improvement Journal.

This module deliberately knows nothing about the Findings Pack or population
rows.  Callers pass the already owner-scoped persisted matches; aggregation is
pure and therefore cannot accidentally blend accounts or invent a comparison
for a missing sample.
"""

from __future__ import annotations

import json
import math
import statistics
from collections import defaultdict
from collections.abc import Iterable, Mapping
from typing import Any, Literal

from .extract_v2 import PARITY_V2_VERSION

Role = Literal["TOP", "JUNGLE", "MIDDLE", "BOTTOM", "UTILITY", "UNKNOWN"]
FeatureStatus = Literal["available", "insufficient-sample", "unavailable"]
FeatureKey = Literal[
    "unseen_recall_share_by_15m",
    "avg_banked_gold_at_recall_by_15m",
    "early_fight_participation_rate",
    "first_dragon_by_20m_s",
    "plates_taken_by_14m",
]

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
FEATURE_KEYS: tuple[FeatureKey, ...] = (
    "unseen_recall_share_by_15m",
    "avg_banked_gold_at_recall_by_15m",
    "early_fight_participation_rate",
    "first_dragon_by_20m_s",
    "plates_taken_by_14m",
)
FEATURE_CAVEATS: dict[FeatureKey, str] = {
    "unseen_recall_share_by_15m": (
        "Descriptive recall-visibility association; not a causal recommendation."
    ),
    "avg_banked_gold_at_recall_by_15m": (
        "Descriptive banked-gold association; not a causal recommendation."
    ),
    "early_fight_participation_rate": (
        "Descriptive participation association; not a causal recommendation."
    ),
    "first_dragon_by_20m_s": (
        "Timing association only; possession and denial are separate objective measures."
    ),
    "plates_taken_by_14m": (
        "Weak, era-sensitive diagnostic association; the 14.x direction differs and is not "
        "significant; not a causal recommendation."
    ),
}
MIN_FEATURE_BASELINE_SAMPLE = 5


def _feature_values(row: Mapping[str, Any], feature_key: FeatureKey) -> tuple[float | None, str]:
    """Read one value only from a declared, nested parity-v2 payload."""
    raw_payload = row.get("features_json")
    payload: Mapping[str, Any] | None = None
    if isinstance(raw_payload, Mapping):
        payload = raw_payload
    elif isinstance(raw_payload, str) and raw_payload.strip():
        try:
            decoded = json.loads(raw_payload)
        except (TypeError, ValueError, json.JSONDecodeError):
            decoded = None
        if isinstance(decoded, Mapping):
            payload = decoded
    if payload is None:
        return None, (
            "Observation unavailable: the persisted row has no readable "
            f"{PARITY_V2_VERSION} feature payload. {FEATURE_CAVEATS[feature_key]}"
        )
    if payload.get("feature_contract_version") != PARITY_V2_VERSION:
        return None, (
            "Observation unavailable: the persisted row does not declare "
            f"{PARITY_V2_VERSION}. {FEATURE_CAVEATS[feature_key]}"
        )
    nested = payload.get("features")
    if not isinstance(nested, Mapping):
        return None, (
            "Observation unavailable: the persisted row has no nested feature "
            f"values. {FEATURE_CAVEATS[feature_key]}"
        )
    value = nested.get(feature_key)
    if not _finite_number(value):
        return None, (
            "Observation unavailable in the required feature window. "
            f"{FEATURE_CAVEATS[feature_key]}"
        )
    return float(value), FEATURE_CAVEATS[feature_key]


def _finite_number(value: object) -> bool:
    return (
        isinstance(value, (int, float))
        and not isinstance(value, bool)
        and math.isfinite(float(value))
    )


def aggregate_feature_insights(
    rows: Iterable[Mapping[str, Any]],
) -> list[dict[str, Any]]:
    """Compare the latest filtered match with prior same-role observations."""
    ordered = sorted(rows, key=_match_sort_key)
    if not ordered:
        return []
    current_row = ordered[-1]
    current_role = _role(current_row.get("role"))
    prior_rows = ordered[:-1]
    result: list[dict[str, Any]] = []
    for feature_key in FEATURE_KEYS:
        current_value, current_caveat = _feature_values(current_row, feature_key)
        baseline_values = [
            value
            for row in prior_rows
            if _role(row.get("role")) == current_role
            for value, _ in [_feature_values(row, feature_key)]
            if value is not None
        ]
        sample_size = len(baseline_values)
        if current_value is None:
            status: FeatureStatus = "unavailable"
            role_baseline = None
            delta = None
            caveat = current_caveat
        elif sample_size < MIN_FEATURE_BASELINE_SAMPLE:
            status = "insufficient-sample"
            role_baseline = None
            delta = None
            caveat = (
                f"Insufficient matching-role prior observations ({sample_size}; "
                f"{MIN_FEATURE_BASELINE_SAMPLE} required). {current_caveat}"
            )
        else:
            role_baseline = statistics.fmean(baseline_values)
            delta = current_value - role_baseline
            status = "available"
            caveat = current_caveat
        result.append(
            {
                "feature_key": feature_key,
                "current_value": current_value,
                "role_baseline": role_baseline,
                "delta": delta,
                "sample_size": sample_size,
                "status": status,
                "caveat": caveat,
            }
        )
    return result


def aggregate_feature_trajectories(
    rows: Iterable[Mapping[str, Any]],
) -> list[dict[str, Any]]:
    """Emit one explicit observation point for every filtered match and key."""
    ordered = sorted(rows, key=_match_sort_key)
    result: list[dict[str, Any]] = []
    for feature_key in FEATURE_KEYS:
        for row in ordered:
            value, caveat = _feature_values(row, feature_key)
            result.append(
                {
                    "feature_key": feature_key,
                    "played_at": _played_at(row.get("played_at")),
                    "value": value,
                    "sample_size": 1 if value is not None else 0,
                    "status": "available" if value is not None else "unavailable",
                    "caveat": caveat,
                }
            )
    return result


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
        if not isinstance(version, str) or not version.strip():
            features = row.get("features")
            if isinstance(features, Mapping):
                version = features.get("feature_contract_version")
            raw_payload = row.get("features_json")
            if (
                (not isinstance(version, str) or not version.strip())
                and isinstance(raw_payload, str)
                and raw_payload.strip()
            ):
                try:
                    decoded = json.loads(raw_payload)
                except (TypeError, ValueError, json.JSONDecodeError):
                    decoded = None
                if isinstance(decoded, Mapping):
                    version = decoded.get("feature_contract_version")
        if isinstance(version, str) and version.strip():
            versions.add(version.strip())
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
        "feature_insights": aggregate_feature_insights(ordered),
        "feature_trajectories": aggregate_feature_trajectories(ordered),
    }
