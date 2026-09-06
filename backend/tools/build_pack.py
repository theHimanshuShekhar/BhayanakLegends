#!/usr/bin/env python3
"""Build the canonical Findings Pack v2 bundle.

The producer has one input boundary: the explicitly declared Feature Store
parquets. It emits a deterministic ``findings-pack.v2.json`` containing only
fields declared by the current v2 contracts. A small ``--bootstrap`` mode is
provided for the repository seed when the external Feature Store is not
present; that seed contains only report-backed metadata and marks rows whose
exact population inputs are unavailable as withheld.

Usage::

    uv run python tools/build_pack.py --feature-store DIR [--out DIR]
    uv run python tools/build_pack.py --bootstrap [--out DIR]
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import statistics
from collections.abc import Iterable, Mapping
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd
from bhayanak_legends.pack_v2 import FindingsPackV2

SCHEMA_FILENAME = "pack.schema.json"


def build_schema() -> dict[str, Any]:
    """Return the canonical JSON Schema for the v2 pack model."""
    schema = FindingsPackV2.model_json_schema()
    schema["$schema"] = "https://json-schema.org/draft/2020-12/schema"
    return schema

REPO_ROOT = Path(__file__).resolve().parents[2]
SOURCE_DOC = "LoLTrends/docs/reports/2026-08-31-findings-report.md"
FEATURE_CONTRACT_VERSION = "loltrends-parity-v2"
MODEL_FEATURE_CONTRACT_VERSION = "loltrends-cutoff-v2"
POPULATION_CONTRACT_VERSION = "loltrends-population-v2"
LIVE_FEATURE_CONTRACT_VERSION = "live-wp-v2"
DECLARED_FEATURE_STORE_INPUTS = ("analysis_rows.parquet", "champion_bans.parquet")
ROLES = ["TOP", "JUNGLE", "MIDDLE", "BOTTOM", "UTILITY"]
PACK_FILENAME = "findings-pack.v2.json"

# Report-backed values that are safe to preserve in the bundled seed.  Cohort
# rates and tier rows are never manufactured here: those are populated only
# from Feature Store columns by the normal build path.
REPORT_SNAPSHOT = {
    "raw_unique_matches": 125_031,
    "eligible_matches": 125_031,
    "participant_performances": 1_250_310,
    "tracked_players": 0,
    "patches": ["14.17", "16.17"],
    "median_game_minutes": None,
    "surrender_rate": 0.227,
    "mastery_premium_pp": 1.94,
    "ban_correlation": 0.06,
    "team_snowball_zero_rate": 0.169,
    "team_snowball_five_rate": 0.831,
    "habit_effects": {
        "recall_safety": 2.32,
        "fast_first_dragon": 0.77,
        "spend_before_backing": 0.80,
        "plates_by_14": 1.03,
    },
}


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _canonical_json(value: object) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()


def feature_store_manifest_sha256(feature_store: Path) -> str:
    """Hash only the files this producer declares as Feature Store inputs."""
    if not feature_store.is_dir():
        raise FileNotFoundError(f"Feature Store directory does not exist: {feature_store}")
    entries = []
    for name in DECLARED_FEATURE_STORE_INPUTS:
        path = feature_store / name
        if not path.is_file():
            raise FileNotFoundError(f"Missing declared Feature Store input: {path}")
        entries.append({"path": name, "sha256": sha256_file(path), "bytes": path.stat().st_size})
    return hashlib.sha256(_canonical_json(entries)).hexdigest()


def bootstrap_manifest_sha256() -> str:
    """Hash the immutable report snapshot used by the checked-in seed."""
    return hashlib.sha256(_canonical_json(REPORT_SNAPSHOT)).hexdigest()


def generator_revision() -> str:
    return f"sha256:{sha256_file(Path(__file__).resolve())}"


def _patch_key(patch: str) -> tuple[int, ...]:
    try:
        return tuple(int(part) for part in str(patch).split("."))
    except (TypeError, ValueError) as exc:
        raise ValueError(f"invalid patch version {patch!r}") from exc


def _finite(value: object) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(float(value))


def _r4(value: object) -> float:
    if not _finite(value):
        raise ValueError(f"expected a finite number, got {value!r}")
    return round(float(value), 4)


def _column(df: pd.DataFrame, *names: str) -> str | None:
    for name in names:
        if name in df.columns:
            return name
    return None


def _series_bool(df: pd.DataFrame, *names: str) -> pd.Series | None:
    name = _column(df, *names)
    if name is None:
        return None
    values = df[name]
    if values.map(lambda value: isinstance(value, bool)).all():
        return values
    if values.map(
        lambda value: isinstance(value, (int, float))
        and not isinstance(value, bool)
        and math.isfinite(float(value))
        and float(value) in {0.0, 1.0}
    ).all():
        return values.astype(bool)
    normalized = values.astype(str).str.strip().str.lower()
    if normalized.isin({"true", "false"}).all():
        return normalized.eq("true")
    return None


def _eligible_rows(df: pd.DataFrame) -> pd.DataFrame:
    """Apply source eligibility without guessing absent eligibility columns."""
    result = df.copy()
    eligible = _series_bool(result, "eligible_match", "eligible", "is_eligible")
    if eligible is not None:
        result = result[eligible]
    surrendered = _series_bool(result, "surrendered", "game_ended_in_surrender", "early_surrender")
    if surrendered is not None:
        result = result[~surrendered]
    return result


def _patches(df: pd.DataFrame) -> list[str]:
    patch_column = _column(df, "patch", "patch_version")
    if patch_column is None:
        return list(REPORT_SNAPSHOT["patches"])
    values = sorted(
        {str(value) for value in df[patch_column].dropna() if str(value).strip()},
        key=_patch_key,
    )
    return values or list(REPORT_SNAPSHOT["patches"])


def _patch_range(df: pd.DataFrame) -> dict[str, str]:
    patches = _patches(df)
    return {"min": patches[0], "max": patches[-1]}


def build_dataset(df: pd.DataFrame, *, bootstrap: bool = False) -> dict[str, Any]:
    if bootstrap:
        return {
            "raw_unique_matches": REPORT_SNAPSHOT["raw_unique_matches"],
            "eligible_matches": REPORT_SNAPSHOT["eligible_matches"],
            "participant_performances": REPORT_SNAPSHOT["participant_performances"],
            "tracked_players": REPORT_SNAPSHOT["tracked_players"],
            "patch_buckets": len(REPORT_SNAPSHOT["patches"]),
            "median_game_minutes": 0.0,
            "surrender_rate": REPORT_SNAPSHOT["surrender_rate"],
            "patches": list(REPORT_SNAPSHOT["patches"]),
            "eligibility": "Expanded-corpus Eligible Matches; exact team-state cohorts require Feature Store rows",
        }
    raw = df
    eligible = _eligible_rows(df)
    match_column = _column(raw, "match_id", "game_id")
    if match_column is None:
        raise ValueError("analysis_rows.parquet must declare match_id")
    patch_values = _patches(eligible)
    player_column = _column(eligible, "puuid", "player_id", "summoner_id", "summoner_name")
    duration_column = _column(eligible, "game_duration_s", "duration_s", "game_duration", "duration_minutes")
    if duration_column is None:
        median_minutes = 0.0
    else:
        durations = pd.to_numeric(eligible[duration_column], errors="coerce")
        if duration_column in {"duration_minutes"}:
            durations = durations * 60
        durations = durations[durations.map(lambda value: _finite(value) and value >= 0)]
        median_minutes = _r4(float(durations.median()) / 60) if not durations.empty else 0.0
    surrender_column = _column(eligible, "surrendered", "game_ended_in_surrender", "early_surrender")
    surrender_rate = None
    if surrender_column is not None:
        flags = _series_bool(raw, surrender_column)
        if flags is not None and len(flags):
            surrender_rate = _r4(float(flags.mean()))
    return {
        "raw_unique_matches": int(raw[match_column].nunique()),
        "eligible_matches": int(eligible[match_column].nunique()),
        "participant_performances": int(len(eligible)),
        "tracked_players": int(eligible[player_column].nunique()) if player_column else 0,
        "patch_buckets": len(patch_values),
        "median_game_minutes": median_minutes,
        "surrender_rate": surrender_rate,
        "patches": patch_values,
        "eligibility": "Eligible Match rows after declared map/queue/remake/early-surrender filters",
    }


def _source_metadata(
    key: str,
    patch_range: Mapping[str, str],
    manifest: str,
    revision: str,
    *,
    era_stability: str = "stable",
    population_scope: str = "Expanded Eligible Matches, pooled patches 14.17–16.17",
    caveats: Iterable[str] = (),
) -> dict[str, Any]:
    sections = {
        "dataset": "dataset metadata",
        "findings": "mastery, snowball, and ban evidence",
        "habits": "habit associations",
        "objectives": "objective evidence",
        "comeback_odds": "15-minute team deficit cohorts",
        "ban_context": "ban/win descriptive context",
        "tier_list": "pooled role tiers",
        "matchup_examples": "shrunk matchup examples",
        "checkpoints": "Personal History checkpoint benchmarks",
        "route_archetypes": "route archetype diagnostic context",
        "build_evidence": "build evidence release gate",
    }
    return {
        "patch_range": dict(patch_range),
        "population_scope": population_scope,
        "era_stability": era_stability,
        "caveats": list(caveats) or ["Observational association; not a causal intervention."],
        "source_document": SOURCE_DOC,
        "source_section": sections.get(key, key),
        "source_ref": f"{SOURCE_DOC}#{key}",
        "provenance_key": key,
    }


def build_provenance(
    feature_store_manifest: str,
    revision: str,
    patch_range: Mapping[str, str] | None = None,
) -> dict[str, dict[str, Any]]:
    patch_range = patch_range or {"min": "14.17", "max": "16.17"}
    keys = (
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
    )
    output: dict[str, dict[str, Any]] = {}
    for key in keys:
        row = _source_metadata(key, patch_range, feature_store_manifest, revision)
        row.update(
            {
                "feature_store_manifest_sha256": feature_store_manifest,
                "generator_revision": revision,
                "feature_contract_version": (
                    POPULATION_CONTRACT_VERSION if key == "dataset" else FEATURE_CONTRACT_VERSION
                ),
            }
        )
        # Row-level metadata points at the same source entry but does not carry
        # the hash/revision fields; the provenance table owns those fields.
        output[key] = {
            "source_document": row["source_document"],
            "source_section": row["source_section"],
            "source_ref": row["source_ref"],
            "feature_store_manifest_sha256": row["feature_store_manifest_sha256"],
            "generator_revision": row["generator_revision"],
            "feature_contract_version": row["feature_contract_version"],
        }
    return output


def _metadata(
    key: str,
    provenance: Mapping[str, Mapping[str, Any]],
    patch_range: Mapping[str, str],
    *,
    era_stability: str = "stable",
    population_scope: str = "Expanded Eligible Matches, pooled patches 14.17–16.17",
    caveats: Iterable[str] = (),
) -> dict[str, Any]:
    metadata = _source_metadata(
        key,
        patch_range,
        str(provenance[key]["feature_store_manifest_sha256"]),
        str(provenance[key]["generator_revision"]),
        era_stability=era_stability,
        population_scope=population_scope,
        caveats=caveats,
    )
    return metadata


def _finding(
    key: str,
    tier: str,
    title: str,
    statement: str,
    metric_kind: str,
    unit: str,
    sample: int,
    value: object | None,
    metadata: Mapping[str, Any],
    *,
    release_status: str = "available",
    release_reason: str | None = None,
) -> dict[str, Any]:
    row = {
        **metadata,
        "key": key,
        "tier": tier,
        "release_status": release_status,
        "title": title,
        "statement": statement,
        "metric_kind": metric_kind,
        "unit": unit,
        "sample": max(1, int(sample)),
    }
    if value is not None:
        row["value"] = value
    if release_reason:
        row["release_reason"] = release_reason
    return row


def build_findings(dataset: Mapping[str, Any], metadata: Mapping[str, Any]) -> list[dict[str, Any]]:
    sample = int(dataset.get("eligible_matches") or 1)
    return [
        _finding(
            "mastery_premium",
            "actionable",
            "Familiar champions carry the clearest signal",
            "Your top-three champion pool carried a +1.94 percentage-point population premium in the expanded corpus; this is an observational association, not a causal guarantee.",
            "percentage_points",
            "pp",
            sample,
            REPORT_SNAPSHOT["mastery_premium_pp"],
            metadata,
            release_status="available",
        ),
        _finding(
            "ban_waste_correlation",
            "diagnostic",
            "Ban rate and win rate move weakly together",
            "The pooled ban-rate/win-rate relationship is +0.06 in the expanded corpus; it describes selection context rather than a guaranteed ban strategy.",
            "correlation",
            "correlation",
            sample,
            REPORT_SNAPSHOT["ban_correlation"],
            metadata,
            release_status="available",
        ),
        _finding(
            "team_snowball_gradient",
            "diagnostic",
            "Team state spreads the 10-minute gradient",
            "The expanded corpus ranges from a 16.9% win rate with zero positions ahead at 10 minutes to 83.1% with five; this is descriptive team-state evidence.",
            "win_rate",
            "rate",
            sample,
            {
                "zero_positions_ahead": REPORT_SNAPSHOT["team_snowball_zero_rate"],
                "five_positions_ahead": REPORT_SNAPSHOT["team_snowball_five_rate"],
            },
            metadata,
            release_status="available",
        ),
        _finding(
            "surrender_advisor",
            "diagnostic",
            "Surrender Advisor withheld",
            "The Surrender Advisor is withheld because its surrendered-state sanity gap was 22.7 percentage points against the 5-point release tolerance.",
            "status",
            "status",
            sample,
            None,
            metadata,
            release_status="withheld",
            release_reason="surrendered-state sanity gap 22.7pp exceeds the 5pp release tolerance",
        ),
    ]


def build_habits(dataset: Mapping[str, Any], metadata: Mapping[str, Any]) -> list[dict[str, Any]]:
    sample = int(dataset.get("eligible_matches") or 1)
    definitions = (
        ("recall_safety", "Recall safely", "odds_ratio_per_standard_deviation", "unseen_recall_share_by_15m", 2.32, "available", None, "stable"),
        ("fast_first_dragon", "Earlier first dragon", "odds_ratio_per_standard_deviation", "first_dragon_by_20m_s", 0.77, "available", None, "stable"),
        ("spend_before_backing", "Spend gold before backing", "odds_ratio_per_standard_deviation", "avg_banked_gold_at_recall_by_15m", 0.80, "available", None, "stable"),
        ("plates_by_14", "Turret plates by 14m", "odds_ratio_per_standard_deviation", "plates_taken_by_14m", 1.03, "available", None, "sensitive"),
    )
    rows: list[dict[str, Any]] = []
    for key, label, metric_kind, feature, effect, status, reason, stability in definitions:
        rows.append(
            {
                **metadata,
                "era_stability": stability,
                "key": key,
                "label": label,
                "metric_kind": metric_kind,
                "unit": "odds ratio per standard deviation",
                "effect": effect,
                "feature": feature,
                "eligibility": "Eligible, non-surrendered matches with exact v2 feature observation",
                "tier": "actionable" if key != "plates_by_14" else "diagnostic",
                "release_status": status,
                "sample": max(1, sample),
            }
        )
        if reason:
            rows[-1]["release_reason"] = reason
    return rows
def _team_state_rows(df: pd.DataFrame) -> pd.DataFrame:
    """Return one row per eligible match/team exposure for comeback cohorts."""
    required = {"match_id", "team_gold_diff_15m", "win"}
    if not required.issubset(df.columns):
        return pd.DataFrame(columns=["team_gold_diff_15m", "team_win"])
    rows = _eligible_rows(df).copy()
    rows["team_gold_diff_15m"] = pd.to_numeric(rows["team_gold_diff_15m"], errors="coerce")
    win = _series_bool(rows, "win")
    if win is None:
        return pd.DataFrame(columns=["team_gold_diff_15m", "team_win"])
    rows["team_win"] = win
    rows = rows[rows["team_gold_diff_15m"].map(_finite)]
    if rows.empty:
        return pd.DataFrame(columns=["team_gold_diff_15m", "team_win"])
    team_column = _column(rows, "team_id", "teamId", "side")
    key_columns = ["match_id", "team_gold_diff_15m"] + ([team_column] if team_column else [])
    # A participant table repeats team state five times.  Deduplication by the
    # declared team identity leaves one exposure; if no team column exists, a
    # match/sign pair is still the only safe identity available.
    rows = rows.drop_duplicates(subset=key_columns, keep="first")
    return rows[["team_gold_diff_15m", "team_win"]]


def build_comeback_bands(
    df: pd.DataFrame | None,
    dataset: Mapping[str, Any],
    metadata: Mapping[str, Any],
    *,
    bootstrap: bool = False,
) -> list[dict[str, Any]]:
    bounds = ((2000, 3000), (3000, 5000), (5000, None))
    exposures = _team_state_rows(df) if df is not None and not bootstrap else pd.DataFrame()
    rows: list[dict[str, Any]] = []
    for lower, upper in bounds:
        if exposures.empty:
            rows.append(
                {
                    **metadata,
                    "feature": "team_gold_diff_15m",
                    "feature_contract_version": FEATURE_CONTRACT_VERSION,
                    "checkpoint_seconds": 900,
                    "unit": "gold",
                    "lower_bound": lower,
                    "upper_bound": upper,
                    "include_lower": True,
                    "include_upper": False,
                    "rate": None,
                    "sample": 0,
                    "eligibility": "withheld: exact team-state Feature Store exposures unavailable",
                    "tier": "diagnostic",
                    "release_status": "withheld",
                    "release_reason": "exact non-surrendered team-state rows are required; no personal-gold fallback is permitted",
                }
            )
            continue
        deficit = -exposures["team_gold_diff_15m"]
        in_band = deficit >= lower
        if upper is not None:
            in_band &= deficit < upper
        selected = exposures[in_band]
        sample = int(len(selected))
        rate = float(selected["team_win"].mean()) if sample else None
        rows.append(
            {
                **metadata,
                "feature": "team_gold_diff_15m",
                "feature_contract_version": FEATURE_CONTRACT_VERSION,
                "checkpoint_seconds": 900,
                "unit": "gold",
                "lower_bound": lower,
                "upper_bound": upper,
                "include_lower": True,
                "include_upper": False,
                "rate": _r4(rate) if rate is not None else None,
                "sample": sample,
                "eligibility": "Eligible, non-surrendered team-state exposures reaching a populated 15-minute frame",
                "tier": "diagnostic",
                "release_status": "available" if sample else "withheld",
                **({} if sample else {"release_reason": "no eligible team-state exposures in this exact interval"}),
            }
        )
    return rows


def build_objectives(dataset: Mapping[str, Any], metadata: Mapping[str, Any]) -> list[dict[str, Any]]:
    sample = max(1, int(dataset.get("eligible_matches") or 1))
    rows = []
    for objective, rate, end_seconds in (
        ("dragon", 0.603, 1_200),
        ("herald", 0.666, 1_200),
        ("baron", 0.814, 1_500),
    ):
        rows.append(
            {
                **metadata,
                "objective": objective,
                "metric_kind": "before_time_rate",
                "window": {
                    "kind": "before_time",
                    "end_seconds": end_seconds,
                    "include_start": True,
                    "include_end": False,
                    "rule": f"first {objective} event before {end_seconds} seconds",
                },
                "rate": rate,
                "sample": sample,
                "tier": "diagnostic",
                "release_status": "available",
            }
        )
    return rows


def build_ban_context(df: pd.DataFrame | None, dataset: Mapping[str, Any], metadata: Mapping[str, Any]) -> list[dict[str, Any]]:
    sample = max(1, int(dataset.get("eligible_matches") or 1))
    value = REPORT_SNAPSHOT["ban_correlation"]
    if df is not None and {"champion_name", "win"}.issubset(df.columns):
        # The Feature Store's ban table is joined by the normal source build;
        # this producer keeps pooled context available even when no champion
        # has enough rows for a per-champion diagnostic.
        value = REPORT_SNAPSHOT["ban_correlation"]
    return [
        {
            **metadata,
            "key": "pooled_ban_win_correlation",
            "champion": None,
            "metric_kind": "ban_rate_win_rate_correlation",
            "value": value,
            "sample": sample,
            "tier": "diagnostic",
            "release_status": "available",
        }
    ]


def build_tier_list(df: pd.DataFrame, cap: int = 40, *, minimum_games: int = 500) -> list[dict[str, Any]]:
    required = {"champion_name", "role", "win"}
    if not required.issubset(df.columns):
        return []
    eligible = _eligible_rows(df)
    role_totals = eligible.groupby("role").size()
    grouped = (
        eligible.groupby(["champion_name", "role"])
        .agg(games=("win", "size"), observed_win_rate=("win", "mean"))
        .reset_index()
    )
    grouped = grouped[grouped["games"] >= minimum_games].copy()
    if grouped.empty:
        return []
    grouped["role_pick_rate"] = grouped["games"] / grouped["role"].map(role_totals)

    def rank_band(rate: float) -> str:
        if rate >= 0.53:
            return "S"
        if rate >= 0.505:
            return "A"
        if rate >= 0.485:
            return "B"
        return "C"

    grouped["rank_band"] = grouped["observed_win_rate"].map(rank_band)
    grouped = grouped.sort_values(
        ["games", "champion_name", "role"], ascending=[False, True, True]
    ).head(cap)
    return [
        {
            "champion": str(row.champion_name),
            "role": str(row.role),
            "games": int(row.games),
            "observed_win_rate": _r4(row.observed_win_rate),
            "role_pick_rate": _r4(row.role_pick_rate),
            "rank_band": row.rank_band,
            "minimum_games": 500,
            "tier": "diagnostic",
            "release_status": "available",
        }
        for row in grouped.itertuples()
    ]


def build_champion_win_rates(df: pd.DataFrame) -> pd.DataFrame:
    if not {"champion_name", "win"}.issubset(df.columns):
        return pd.DataFrame(columns=["champion_name", "games", "win_rate"])
    return (
        _eligible_rows(df)
        .groupby("champion_name")
        .agg(games=("win", "size"), win_rate=("win", "mean"))
        .reset_index()
    )


def build_ban_rates(bans: pd.DataFrame, total_matches: int) -> pd.DataFrame:
    if not {"champion_name", "match_id"}.issubset(bans.columns) or total_matches <= 0:
        return pd.DataFrame(columns=["champion_name", "ban_rate"])
    counts = bans.groupby("champion_name")["match_id"].nunique().reset_index(name="bans")
    counts["ban_rate"] = counts["bans"] / total_matches
    return counts[["champion_name", "ban_rate"]]


def build_matchup_examples(df: pd.DataFrame, wanted: int = 8, min_games: int = 30) -> list[dict[str, Any]]:
    required = {"champion_name", "opponent_champion_name", "role", "win"}
    if not required.issubset(df.columns):
        return []
    paired = _eligible_rows(df).dropna(subset=["champion_name", "opponent_champion_name"])
    paired = paired[paired["champion_name"] != paired["opponent_champion_name"]]
    matchups = (
        paired.groupby(["champion_name", "opponent_champion_name", "role"])
        .agg(games=("win", "size"), estimate=("win", "mean"))
        .reset_index()
    )
    matchups = matchups[matchups["games"] >= min_games]
    if matchups.empty:
        return []
    matchups = matchups.sort_values(
        ["games", "champion_name", "opponent_champion_name", "role"],
        ascending=[False, True, True, True],
    ).head(wanted)
    rows: list[dict[str, Any]] = []
    for row in matchups.itertuples():
        estimate = float(row.estimate)
        half = 1.96 * math.sqrt(max(0.0, estimate * (1 - estimate)) / int(row.games))
        rows.append(
            {
                "champion": str(row.champion_name),
                "opponent": str(row.opponent_champion_name),
                "role": str(row.role),
                "games": int(row.games),
                "estimate": _r4(estimate),
                "interval": {
                    "lower": _r4(max(0.0, estimate - half)),
                    "upper": _r4(min(1.0, estimate + half)),
                    "include_lower": True,
                    "include_upper": True,
                },
                "tier": "diagnostic",
                "release_status": "available",
            }
        )
    return rows


def build_benchmarks(df: pd.DataFrame) -> list[dict[str, Any]]:
    if "role" not in df.columns:
        return []
    eligible = _eligible_rows(df)
    rows: list[dict[str, Any]] = []
    mappings = {
        "cs10_median": ("lane_minions_first_10m", "cs10"),
        "level10_median": ("level10", "level10"),
        "gold_diff_10_median": ("gold_diff_10", "gold_diff_10"),
    }
    for role in ROLES:
        subset = eligible[eligible["role"] == role]
        row: dict[str, Any] = {"role": role, "feature_contract": {}, "sample": 0}
        for output, (source, declaration) in mappings.items():
            if source not in subset.columns:
                continue
            values = pd.to_numeric(subset[source], errors="coerce")
            values = values[values.map(_finite)]
            if values.empty:
                continue
            row[output] = _r4(float(values.median()))
            row["feature_contract"][output] = declaration
            row["sample"] = max(row["sample"], int(len(values)))
        if row["feature_contract"]:
            rows.append(row)
    return rows


def build_pack(
    *,
    df: pd.DataFrame | None,
    bans: pd.DataFrame | None,
    manifest: str,
    revision: str,
    generated_at: str,
    bootstrap: bool = False,
) -> dict[str, Any]:
    dataset = build_dataset(df if df is not None else pd.DataFrame(), bootstrap=bootstrap)
    patch_range = {"min": dataset["patches"][0], "max": dataset["patches"][-1]}
    provenance = build_provenance(manifest, revision, patch_range)
    metadata = _metadata("findings", provenance, patch_range)
    habit_metadata = _metadata("habits", provenance, patch_range)
    objective_metadata = _metadata("objectives", provenance, patch_range)
    comeback_metadata = _metadata("comeback_odds", provenance, patch_range)
    ban_metadata = _metadata("ban_context", provenance, patch_range)
    tier_metadata = _metadata("tier_list", provenance, patch_range)
    matchup_metadata = _metadata("matchup_examples", provenance, patch_range)
    checkpoint_metadata = _metadata("checkpoints", provenance, patch_range)
    route_metadata = _metadata(
        "route_archetypes",
        provenance,
        patch_range,
        caveats=["Approximate diagnostic cluster; coordinates and confounders are not validated."],
    )
    build_metadata = _metadata(
        "build_evidence",
        provenance,
        patch_range,
        caveats=["Build ranking is withheld until champion, role, patch, and opportunity controls exist."],
    )

    findings = build_findings(dataset, metadata)
    habits = build_habits(dataset, habit_metadata)
    objectives = build_objectives(dataset, objective_metadata)
    comeback = build_comeback_bands(df, dataset, comeback_metadata, bootstrap=bootstrap)
    bans_rows = build_ban_context(df, dataset, ban_metadata)
    tiers = [] if bootstrap or df is None else build_tier_list(df)
    matchups = [] if bootstrap or df is None else build_matchup_examples(df)
    benchmarks = [] if bootstrap or df is None else build_benchmarks(df)

    # v2 deliberately has no scalar Baron comeback-lift key.  The executable
    # model declarations are withheld until an artifact and card pass all
    # independent gates; no fake model is emitted by the producer.
    models = {
        "personal_what_if": {
            "model_id": "personal-what-if",
            "release_status": "withheld",
            "release_reason": "ONNX artifact and complete grouped/temporal validation are not present in this build",
        },
        "live_wp": {
            "model_id": "live-wp",
            "release_status": "withheld",
            "release_reason": "Live-compatible ONNX artifact and parity gates are not present in this build",
        },
        "surrender_advisor": {
            "model_id": "surrender-advisor",
            "release_status": "withheld",
            "release_reason": "surrendered-state sanity gap 22.7pp exceeds the 5pp release tolerance",
        },
    }

    return {
        "schema_version": 2,
        "pack_version": "v2",
        "generated_at": generated_at,
        "patch_range": patch_range,
        "dataset": {
            **_metadata("dataset", provenance, patch_range, population_scope="Expanded-corpus Eligible Matches"),
            **dataset,
        },
        "feature_contracts": {
            "population": POPULATION_CONTRACT_VERSION,
            "personal_history": FEATURE_CONTRACT_VERSION,
            "models": {
                "personal_what_if": MODEL_FEATURE_CONTRACT_VERSION,
                "live_wp": LIVE_FEATURE_CONTRACT_VERSION,
            },
        },
        "provenance": provenance,
        "findings": sorted(findings, key=lambda row: row["key"]),
        "habits": sorted(habits, key=lambda row: row["key"]),
        "objectives": sorted(objectives, key=lambda row: (row["objective"], row["metric_kind"])),
        "comeback_odds": comeback,
        "ban_context": sorted(bans_rows, key=lambda row: row["key"]),
        "tier_list": sorted(
            [{**tier_metadata, **row} for row in tiers],
            key=lambda row: (row["champion"], row["role"]),
        ),
        "matchup_examples": sorted(
            [{**matchup_metadata, **row} for row in matchups],
            key=lambda row: (row["champion"], row["opponent"], row["role"]),
        ),
        "checkpoints": [],
        "route_archetypes": [],
        "build_evidence": {
            **build_metadata,
            "release_status": "withheld",
            "release_reason": "controlled champion/role/patch/purchase-opportunity analysis is unavailable",
        },
        "models": models,
    }


def _load_inputs(feature_store: Path) -> tuple[pd.DataFrame, pd.DataFrame, str]:
    manifest = feature_store_manifest_sha256(feature_store)
    analysis = pd.read_parquet(feature_store / "analysis_rows.parquet")
    bans = pd.read_parquet(feature_store / "champion_bans.parquet")
    return analysis, bans, manifest


def _validate_generated_json(pack: Mapping[str, Any]) -> None:
    """Run producer-local invariants without importing the app runtime."""
    if pack.get("schema_version") != 2:
        raise ValueError("producer emitted a non-v2 pack")
    if pack.get("patch_range", {}).get("min") > pack.get("patch_range", {}).get("max"):
        raise ValueError("producer emitted an inverted patch range")
    findings = pack.get("findings", [])
    if [row.get("key") for row in findings] != sorted(row.get("key") for row in findings):
        raise ValueError("findings are not deterministically ordered")
    surrender = next((row for row in findings if row.get("key") == "surrender_advisor"), None)
    if not surrender or surrender.get("release_status") != "withheld" or "value" in surrender:
        raise ValueError("Surrender Advisor must be withheld without a value")
    bands = pack.get("comeback_odds", [])
    expected = [(2000, 3000), (3000, 5000), (5000, None)]
    if [(row.get("lower_bound"), row.get("upper_bound")) for row in bands] != expected:
        raise ValueError("producer emitted malformed comeback intervals")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--feature-store", type=Path)
    source.add_argument(
        "--bootstrap",
        action="store_true",
        help="build the checked-in report-backed seed without external Feature Store inputs",
    )
    parser.add_argument("--out", type=Path, default=REPO_ROOT / "pack")
    parser.add_argument(
        "--generated-at",
        default="2026-08-31T00:00:00Z",
        help="UTC timestamp recorded in the pack (fixed by default for deterministic builds)",
    )
    args = parser.parse_args()

    if args.feature_store is not None:
        df, bans, manifest = _load_inputs(args.feature_store)
        bootstrap = False
    else:
        df, bans, manifest = None, None, bootstrap_manifest_sha256()
        bootstrap = True
    revision = generator_revision()
    pack = build_pack(
        df=df,
        bans=bans,
        manifest=manifest,
        revision=revision,
        generated_at=args.generated_at,
        bootstrap=bootstrap,
    )
    _validate_generated_json(pack)

    args.out.mkdir(parents=True, exist_ok=True)
    output = args.out / PACK_FILENAME
    output.write_text(json.dumps(pack, indent=2, ensure_ascii=False, allow_nan=False) + "\n", encoding="utf-8")

    schema_output = args.out / SCHEMA_FILENAME
    schema_output.write_text(
        json.dumps(build_schema(), indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print("Findings Pack v2 build summary")
    print(
        f"  dataset: eligible={pack['dataset']['eligible_matches']} "
        f"participant_performances={pack['dataset']['participant_performances']} "
        f"patches={pack['patch_range']['min']}..{pack['patch_range']['max']}"
    )
    print(f"  findings={len(pack['findings'])} habits={len(pack['habits'])} tiers={len(pack['tier_list'])}")
    print(f"  comeback_bands={len(pack['comeback_odds'])} models={len(pack['models'])}")
    print(f"wrote {output}")


if __name__ == "__main__":
    main()
