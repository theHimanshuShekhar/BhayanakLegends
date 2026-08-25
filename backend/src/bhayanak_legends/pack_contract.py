from __future__ import annotations

import math
from collections.abc import Mapping
from numbers import Real
from typing import Any

_BENCHMARK_MEDIANS = ("cs10_median", "level10_median", "gold_diff_10_median")


def _finite_number(value: object) -> bool:
    return isinstance(value, Real) and not isinstance(value, bool) and math.isfinite(float(value))


def validate_matchup_examples(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    seen: set[tuple[object, object, object]] = set()
    for row in rows:
        champion = row.get("champion")
        opponent = row.get("opponent")
        role = row.get("role")
        if champion == opponent:
            raise ValueError(f"self-matchup is not valid: {champion!r}")
        key = (champion, opponent, role)
        if key in seen:
            raise ValueError(f"duplicate matchup direction: {key!r}")
        seen.add(key)
    return rows


def validate_benchmarks(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    for row in rows:
        feature_contract = row.get("feature_contract")
        if not isinstance(feature_contract, Mapping) or not feature_contract:
            raise ValueError("benchmark feature_contract must be nonempty")
        for median in _BENCHMARK_MEDIANS:
            has_median = median in row
            has_declaration = median in feature_contract
            if has_median != has_declaration:
                raise ValueError(f"benchmark field pairing is incomplete: {median}")
            if has_median and not _finite_number(row[median]):
                raise ValueError(f"benchmark median must be finite: {median}")
            if has_declaration and (
                not isinstance(feature_contract[median], str) or not feature_contract[median]
            ):
                raise ValueError(f"benchmark declaration must be nonempty: {median}")
    return rows


def validate_pack_semantics(pack: Mapping[str, Any]) -> None:
    validate_matchup_examples(pack.get("matchup_examples", []))
    validate_benchmarks(pack.get("benchmarks", []))
