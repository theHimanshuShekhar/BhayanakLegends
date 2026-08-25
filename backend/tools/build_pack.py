#!/usr/bin/env python3
"""Build the Findings Pack v1 (pack/findings-pack.v1.json) for Bhayanak Legends.

Two data sources, nothing else:
  1. Curated findings hardcoded below, each traced to
     companion-app-content.md via source_ref.
  2. Data-driven tables computed from the explicitly declared LoLTrends Feature
     Store parquets (analysis_rows.parquet, champion_bans.parquet).

Deterministic: fixed sort keys and rounding everywhere. Diagnostic statements
never instruct (ADR-0003) — enforced by backend/tests/test_pack.py. Provenance
records the canonical input manifest and generator source hash.

Usage:
  uv run python tools/build_pack.py --feature-store DIR [--out DIR]
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

from bhayanak_legends.pack_contract import _finite_number, validate_benchmarks, validate_matchup_examples

REPO_ROOT = Path(__file__).resolve().parents[2]
SOURCE_DOC = "companion-app-content.md"
FEATURE_CONTRACT_VERSION = "loltrends-parity-v1"
DECLARED_FEATURE_STORE_INPUTS = ("analysis_rows.parquet", "champion_bans.parquet")
ROLES = ["TOP", "JUNGLE", "MIDDLE", "BOTTOM", "UTILITY"]


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def feature_store_manifest_sha256(feature_store: Path) -> str:
    """Hash the canonical manifest of the files this generator declares as inputs."""
    if not feature_store.is_dir():
        raise FileNotFoundError(f"Feature Store directory does not exist: {feature_store}")
    entries = []
    for name in DECLARED_FEATURE_STORE_INPUTS:
        path = feature_store / name
        if not path.is_file():
            raise FileNotFoundError(f"Missing declared Feature Store input: {path}")
        entries.append({"path": name, "sha256": sha256_file(path), "bytes": path.stat().st_size})
    manifest = json.dumps(entries, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(manifest).hexdigest()


def generator_revision() -> str:
    """Identify the exact generator source used for a pack build."""
    return f"sha256:{sha256_file(Path(__file__).resolve())}"


PROVENANCE_SOURCES = {
    "dataset": "6",
    "findings": "1,2,3,7,12,14,24,30",
    "habits": "2.11",
    "objectives": "2.10",
    "comeback_odds": "2.8",
    "ban_advisor": "1.2",
    "trap_picks": "1.4,2.14",
    "tier_list": "1.4,3.15",
    "matchup_examples": "1.3,3.16",
    "benchmarks": "4.26",
    "checkpoints": "2.6",
}


def build_provenance(feature_store_manifest: str, revision: str) -> dict[str, dict[str, str]]:
    return {
        table: {
            "source_document": SOURCE_DOC,
            "source_section": section,
            "feature_store_manifest_sha256": feature_store_manifest,
            "generator_revision": revision,
            "feature_contract_version": FEATURE_CONTRACT_VERSION,
        }
        for table, section in PROVENANCE_SOURCES.items()
    }


def ref(section: int) -> str:
    return f"{SOURCE_DOC}#{section}"


def finding(key: str, tier: str, title: str, statement: str, value: float, unit: str, section: int) -> dict:
    return {
        "key": key,
        "tier": tier,
        "title": title,
        "statement": statement,
        "value": value,
        "unit": unit,
        "source_ref": ref(section),
    }


# ---------------------------------------------------------------------------
# Curated findings — every number printed in companion-app-content.md.
# Tier discipline: diagnostic statements describe only, never instruct.
# ---------------------------------------------------------------------------

CURATED_FINDINGS = [
    finding(
        "mastery_premium",
        "actionable",
        "Pocket picks pay",
        "Games on your top-3 champions win 50.6% vs 46.9% on the rest of your pool (+3.7pp); show pocket picks with their win rates.",
        3.7,
        "pp",
        1,
    ),
    finding(
        "ban_waste_correlation",
        "actionable",
        "Most bans are wasted",
        "Population ban-rate vs win-rate correlation is only +0.125: spend bans on actually-strong champions that sail through unbanned instead of fear-bans.",
        0.125,
        "correlation",
        2,
    ),
    finding(
        "counterpick_honesty",
        "diagnostic",
        "Counterpicking is the smallest lever",
        "Empirical-Bayes shrunk lane matchup ratings span roughly ±2.5pp from worst pairing to best; ratings ship with credible intervals because the lever is small.",
        2.5,
        "pp",
        3,
    ),
    finding(
        "level_over_farm_signal",
        "diagnostic",
        "Level lead outranks CS lead",
        "Level lead over the lane opponent outranks CS advantage as a win signal in every role; the jungle role is most sensitive (0.43 vs 0.33).",
        0.43,
        "correlation",
        12,
    ),
    finding(
        "lanes_ahead_meter",
        "diagnostic",
        "Team snowball meter",
        "Zero lanes ahead at 10 minutes converts to a 16.4% win rate and five lanes ahead to 83.8%; spread leads beat stacked ones (60.4% vs 69.7% when a majority lead).",
        83.8,
        "%",
        7,
    ),
    finding(
        "smite_contest_trap",
        "diagnostic",
        "Smite contests are a thermometer, not a thermostat",
        "Even-games fights over the Smite hitpoint race show an adjusted odds ratio of 0.57; most of those fights are lost 50/50 coin flips and the gap widens when already ahead.",
        0.57,
        "adjusted_or",
        14,
    ),
    finding(
        "lane_win_conversion_gap",
        "actionable",
        "Lane leads are raw material",
        "Real cases turned +121g@10 lane leads into 42.7% win rates, so a lane lead pays off only once converted into team gold and objectives.",
        42.7,
        "%",
        24,
    ),
    finding(
        "duo_stacking_null",
        "diagnostic",
        "Duo stacking shows no benefit",
        "Stacked games went 48.4% versus 49.5% with a solo friend, and the gap shrinks across eras — no evidence that queuing together helps.",
        48.4,
        "%",
        30,
    ),
]

# The four surviving habits. effect_per_sd encoded exactly as printed in the doc;
# fast_first_dragon ×0.83 per SD means earlier first dragon is better.
HABITS = [
    {"key": "recall_safety", "label": "Recall safely", "effect_per_sd": 2.24},
    {"key": "fast_first_dragon", "label": "Fast first dragon", "effect_per_sd": 0.83},
    {"key": "spend_before_backing", "label": "Spend gold before backing", "effect_per_sd": 0.88},
    {"key": "plates_by_14", "label": "Turret plates by 14m", "effect_per_sd": 1.08},
]

OBJECTIVES = {
    "baron_pre25_win_rate": 0.814,
    "baron_comeback_lift_pp": 29.5,
    "dragon_denial_win_rate": 0.954,
    "first_dragon_pre20_win_rate": 0.603,
    "herald_pre20_win_rate": 0.666,
}

COMEBACK_ODDS = [
    {"gold_deficit_at_15": -2000, "win_rate": 0.276},
    {"gold_deficit_at_15": -5000, "win_rate": 0.076},
    {"gold_deficit_at_15": -7000, "win_rate": 0.03},
]

CHECKPOINTS = [
    {"gold_diff_bucket": "bottom_quartile_@20m", "win_rate": 0.282},
    {"gold_diff_bucket": "top_quartile_@20m", "win_rate": 0.718},
]


def patch_key(patch: str) -> tuple[int, ...]:
    return tuple(int(part) for part in patch.split("."))


def r4(x: float) -> float:
    return round(float(x), 4)


def build_dataset(df: pd.DataFrame) -> dict:
    patches = sorted(df["patch"].unique(), key=patch_key)
    return {
        "matches": int(df["match_id"].nunique()),
        "player_games": int(len(df)),
        "patches": [patches[0], patches[-1]],
    }


def build_tier_list(df: pd.DataFrame, cap: int = 40) -> list[dict]:
    role_totals = df.groupby("role").size()
    grouped = (
        df.groupby(["champion_name", "role"])
        .agg(games=("win", "size"), win_rate=("win", "mean"))
        .reset_index()
    )
    eligible = grouped[grouped["games"] >= 100].copy()
    eligible["pick_rate"] = eligible["games"] / eligible["role"].map(role_totals)

    def tier_of(wr: float) -> str:
        if wr >= 0.53:
            return "S"
        if wr >= 0.505:
            return "A"
        if wr >= 0.485:
            return "B"
        return "C"

    eligible["tier"] = eligible["win_rate"].map(tier_of)
    eligible = eligible.sort_values(
        ["games", "champion_name", "role"], ascending=[False, True, True]
    ).head(cap)
    return [
        {
            "champion": row.champion_name,
            "role": row.role,
            "games": int(row.games),
            "pick_rate": r4(row.pick_rate),
            "win_rate": r4(row.win_rate),
            "tier": row.tier,
        }
        for row in eligible.itertuples()
    ]


def build_champion_win_rates(df: pd.DataFrame) -> pd.DataFrame:
    rates = (
        df.groupby("champion_name")
        .agg(games=("win", "size"), win_rate=("win", "mean"))
        .reset_index()
    )
    return rates[rates["games"] >= 100].reset_index(drop=True)


def build_ban_rates(bans: pd.DataFrame, total_matches: int) -> pd.DataFrame:
    counts = bans.groupby("champion_name")["match_id"].nunique().reset_index(name="bans")
    counts["ban_rate"] = counts["bans"] / total_matches
    return counts[["champion_name", "ban_rate"]]


def build_ban_advisor(rates: pd.DataFrame, ban_rates: pd.DataFrame) -> list[dict]:
    merged = rates.merge(ban_rates, on="champion_name")
    real_threat = merged[(merged["win_rate"] >= 0.52) & (merged["ban_rate"] <= 0.03)]
    real_threat = real_threat.sort_values(
        ["win_rate", "ban_rate", "champion_name"], ascending=[False, False, True]
    ).head(6)
    # Snowball flag is not derivable from the Feature Store, so high-ban low-WR
    # champions get recommendation "skip" rather than an invented fear-ban flag.
    fear_ban = merged[(merged["ban_rate"] >= 0.15) & (merged["win_rate"] <= 0.48)]
    fear_ban = fear_ban.sort_values(
        ["ban_rate", "win_rate", "champion_name"], ascending=[False, False, True]
    ).head(6)
    rows = []
    for source, recommendation in ((real_threat, "real-threat"), (fear_ban, "skip")):
        for row in source.itertuples():
            rows.append(
                {
                    "champion": row.champion_name,
                    "win_rate": r4(row.win_rate),
                    "ban_rate": r4(row.ban_rate),
                    "recommendation": recommendation,
                }
            )
    return rows


def build_trap_picks(rates: pd.DataFrame, cap: int = 5) -> list[dict]:
    bottom = rates.sort_values(
        ["win_rate", "games", "champion_name"], ascending=[True, False, True]
    ).head(cap)
    return [{"champion": row.champion_name, "win_rate": r4(row.win_rate)} for row in bottom.itertuples()]


def build_matchup_examples(df: pd.DataFrame, wanted: int = 8, min_games: int = 30) -> list[dict]:
    paired = df.dropna(subset=["champion_name", "opponent_champion_name"])
    paired = paired[paired["champion_name"] != paired["opponent_champion_name"]]
    matchups = (
        paired.groupby(["champion_name", "opponent_champion_name", "role"])
        .agg(games=("win", "size"), wr=("win", "mean"))
        .reset_index()
    )
    matchups = matchups[matchups["games"] >= min_games]
    if matchups.empty:
        return []

    def ci_half_width_pp(wr: float, games: int) -> float:
        return round(1.96 * math.sqrt(wr * (1 - wr) / games) * 100, 1)

    picked: list[pd.Series] = []
    pools = {
        role: matchups[matchups["role"] == role].sort_values(
            ["games", "champion_name", "opponent_champion_name"],
            ascending=[False, True, True],
        )
        for role in ROLES
    }
    rank = 0
    while len(picked) < wanted:
        progressed = False
        for role in ROLES:
            pool = pools[role]
            if rank < len(pool):
                picked.append(pool.iloc[rank])
                progressed = True
                if len(picked) >= wanted:
                    break
        if not progressed:
            break
        rank += 1

    rows = [
        {
            "champion": row["champion_name"],
            "opponent": row["opponent_champion_name"],
            "role": row["role"],
            "wr": r4(row["wr"]),
            "ci": ci_half_width_pp(row["wr"], int(row["games"])),
            "games": int(row["games"]),
        }
        for row in picked
    ]
    return validate_matchup_examples(rows)


def build_benchmarks(df: pd.DataFrame) -> list[dict]:
    rows = []
    cs_col = "lane_minions_first_10m"
    for role in ROLES:
        subset = df[df["role"] == role]
        if cs_col not in subset.columns:
            continue
        values = pd.to_numeric(subset[cs_col], errors="coerce")
        values = values[values.map(_finite_number)]
        if values.empty:
            continue
        rows.append(
            {
                "role": role,
                "cs10_median": round(float(values.median()), 1),
                "feature_contract": {"cs10_median": cs_col},
                "sample": int(len(values)),
            }
        )
    return validate_benchmarks(rows)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--feature-store", type=Path, required=True)
    parser.add_argument("--out", type=Path, default=REPO_ROOT / "pack")
    args = parser.parse_args()

    analysis_path = args.feature_store / "analysis_rows.parquet"
    bans_path = args.feature_store / "champion_bans.parquet"
    manifest_sha256 = feature_store_manifest_sha256(args.feature_store)
    revision = generator_revision()


    df = pd.read_parquet(
        analysis_path,
        columns=[
            "match_id",
            "champion_name",
            "opponent_champion_name",
            "role",
            "win",
            "patch",
            "lane_minions_first_10m",
        ],
    )
    bans = pd.read_parquet(bans_path, columns=["match_id", "champion_name"])

    dataset = build_dataset(df)
    champion_rates = build_champion_win_rates(df)
    ban_rates = build_ban_rates(bans, dataset["matches"])

    pack = {
        "schema_version": 1,
        "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "provenance": build_provenance(manifest_sha256, revision),
        "dataset": dataset,
        "findings": CURATED_FINDINGS,
        "habits": HABITS,
        "objectives": OBJECTIVES,
        "comeback_odds": COMEBACK_ODDS,
        "ban_advisor": build_ban_advisor(champion_rates, ban_rates),
        "trap_picks": build_trap_picks(champion_rates),
        "tier_list": build_tier_list(df),
        "matchup_examples": build_matchup_examples(df),
        "benchmarks": build_benchmarks(df),
        "checkpoints": CHECKPOINTS,
    }

    args.out.mkdir(parents=True, exist_ok=True)
    out_path = args.out / "findings-pack.v1.json"
    out_path.write_text(json.dumps(pack, indent=2, ensure_ascii=False) + "\n")

    recommendations = {}
    for row in pack["ban_advisor"]:
        recommendations[row["recommendation"]] = recommendations.get(row["recommendation"], 0) + 1
    rec_summary = ", ".join(f"{k}={v}" for k, v in sorted(recommendations.items())) or "empty"
    print("Findings Pack v1 build summary")
    print(f"  dataset: matches={dataset['matches']} player_games={dataset['player_games']} "
          f"patches={dataset['patches'][0]}..{dataset['patches'][1]}")
    print("  row counts:")
    print(f"    findings           {len(pack['findings'])}")
    print(f"    habits             {len(pack['habits'])}")
    print(f"    ban_advisor        {len(pack['ban_advisor'])} ({rec_summary})")
    print(f"    trap_picks         {len(pack['trap_picks'])}")
    print(f"    tier_list          {len(pack['tier_list'])}")
    print(f"    matchup_examples   {len(pack['matchup_examples'])}")
    print(f"    benchmarks         {len(pack['benchmarks'])}")
    print(f"    comeback_odds      {len(pack['comeback_odds'])}")
    print(f"    checkpoints        {len(pack['checkpoints'])}")
    print("  benchmark medians:")
    for row in pack["benchmarks"]:
        print(f"    {row['role']:<8} cs10={row['cs10_median']} sample={row['sample']}")
    print(f"wrote {out_path}")


if __name__ == "__main__":
    main()
