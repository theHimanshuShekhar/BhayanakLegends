from __future__ import annotations

import json
from pathlib import Path
from fastapi.testclient import TestClient
from pytest import approx

from bhayanak_legends.app import create_app
from bhayanak_legends.config import SidecarConfig
from bhayanak_legends.insights import aggregate_feature_insights, aggregate_feature_trajectories, aggregate_insights

AUTH = {
    "X-BL-Token": "local-sidecar-development-token-32chars",
    "Host": "127.0.0.1:23110",
}
VERSION = "loltrends-parity-v2"
FEATURE_KEYS = (
    "unseen_recall_share_by_15m",
    "avg_banked_gold_at_recall_by_15m",
    "early_fight_participation_rate",
    "first_dragon_by_20m_s",
    "plates_taken_by_14m",
)


def payload(index: int | None, *, version: str = VERSION) -> str:
    values = {
        "unseen_recall_share_by_15m": 0.2 + (index or 0) / 100,
        "avg_banked_gold_at_recall_by_15m": 300 + (index or 0) * 10,
        "early_fight_participation_rate": 0.3 + (index or 0) / 100,
        "first_dragon_by_20m_s": 480 + (index or 0) * 5,
        "plates_taken_by_14m": 1 + (index or 0) % 3,
    }
    if index is None:
        values["first_dragon_by_20m_s"] = None
    return json.dumps({"feature_contract_version": version, "features": values})


def row(
    match_id: str,
    index: int | None,
    *,
    played_at: str,
    role: str = "MIDDLE",
    champion: str = "Ahri",
    version: str = VERSION,
) -> dict:
    return {
        "match_id": match_id,
        "played_at": played_at,
        "role": role,
        "champion": champion,
        "win": index is not None and index % 2 == 0,
        "features_json": payload(index, version=version),
    }


def test_feature_comparison_uses_latest_value_and_excludes_it_from_role_baseline() -> None:
    rows = [
        row(f"prior-{index}", index, played_at=f"2026-01-01T00:0{index}:00Z")
        for index in range(5)
    ]
    rows.append(row("current", 9, played_at="2026-01-01T00:09:00Z"))

    result = aggregate_feature_insights(rows)
    by_key = {entry["feature_key"]: entry for entry in result}

    assert tuple(by_key) == FEATURE_KEYS
    early = by_key["early_fight_participation_rate"]
    assert early["current_value"] == 0.39
    assert early["role_baseline"] == approx(0.32)
    assert early["delta"] == approx(0.07)
    assert early["sample_size"] == 5
    assert early["status"] == "available"


def test_feature_comparison_keeps_current_value_when_prior_role_sample_is_insufficient() -> None:
    rows = [
        row("prior", 1, played_at="2026-01-01T00:00:00Z"),
        row("other-role", 2, played_at="2026-01-01T00:01:00Z", role="TOP"),
        row("current", 9, played_at="2026-01-01T00:02:00Z"),
    ]

    result = aggregate_feature_insights(rows)
    early = next(entry for entry in result if entry["feature_key"] == "early_fight_participation_rate")

    assert early["current_value"] == 0.39
    assert early["role_baseline"] is None
    assert early["delta"] is None
    assert early["sample_size"] == 1
    assert early["status"] == "insufficient-sample"
    assert "Insufficient matching-role" in early["caveat"]


def test_missing_current_value_is_unavailable_but_trajectory_keeps_every_match() -> None:
    rows = [
        row("prior", 1, played_at="2026-01-01T00:00:00Z"),
        row("current", None, played_at="2026-01-01T00:01:00Z"),
    ]

    comparison = aggregate_feature_insights(rows)
    dragon = next(entry for entry in comparison if entry["feature_key"] == "first_dragon_by_20m_s")
    assert dragon["current_value"] is None
    assert dragon["role_baseline"] is None
    assert dragon["delta"] is None
    assert dragon["sample_size"] == 1
    assert dragon["status"] == "unavailable"

    trajectory = aggregate_feature_trajectories(rows)
    dragon_points = [entry for entry in trajectory if entry["feature_key"] == "first_dragon_by_20m_s"]
    assert [entry["played_at"] for entry in dragon_points] == [
        "2026-01-01T00:00:00Z",
        "2026-01-01T00:01:00Z",
    ]
    assert [entry["value"] for entry in dragon_points] == [485.0, None]
    assert dragon_points[1]["status"] == "unavailable"


def build_client(tmp_path: Path) -> TestClient:
    config = SidecarConfig(
        port=23110,
        token=AUTH["X-BL-Token"],
        data_dir=tmp_path / "data",
        pack_dir=tmp_path / "empty-pack",
    )
    return TestClient(create_app(config))


def seed(store, match_id: str, *, owner_key: str, played_at: str, index: int | None, role: str = "MIDDLE") -> None:
    store.upsert_match(
        match_id,
        played_at,
        "16.7",
        role,
        "Ahri",
        index is not None and index % 2 == 0,
        1800,
        payload(index),
        owner_key=owner_key,
    )


def test_history_insights_api_returns_owner_scoped_feature_comparisons_and_trajectories(tmp_path: Path) -> None:
    client = build_client(tmp_path)
    store = client.app.state.store
    owner_a = store.owner_key_for_puuid("puuid-a")
    owner_b = store.owner_key_for_puuid("puuid-b")
    generation = store.begin_owner_transition("resolving")
    store.activate_owner("puuid-a", "PlayerA#TAG", "sea", generation)
    for index in range(5):
        seed(store, f"a-prior-{index}", owner_key=owner_a, played_at=f"2026-01-01T00:0{index}:00Z", index=index)
    seed(store, "a-current", owner_key=owner_a, played_at="2026-01-01T00:09:00Z", index=9)
    seed(store, "b-current", owner_key=owner_b, played_at="2026-01-01T00:10:00Z", index=99)

    with client:
        response = client.get("/history/insights", headers=AUTH)

    assert response.status_code == 200
    body = response.json()
    assert body["feature_contract_version"] == VERSION
    assert body["feature_contract_status"] == "available"
    assert [entry["feature_key"] for entry in body["feature_insights"]] == list(FEATURE_KEYS)
    early = next(entry for entry in body["feature_insights"] if entry["feature_key"] == "early_fight_participation_rate")
    assert early["current_value"] == 0.39
    assert early["role_baseline"] == approx(0.32)
    assert early["sample_size"] == 5
    assert len(body["feature_trajectories"]) == len(FEATURE_KEYS) * 6
    assert all("b-current" not in entry["played_at"] for entry in body["feature_trajectories"])


def test_aggregate_insights_adds_empty_feature_arrays_for_empty_history() -> None:
    result = aggregate_insights([])

    assert result["feature_insights"] == []
    assert result["feature_trajectories"] == []
