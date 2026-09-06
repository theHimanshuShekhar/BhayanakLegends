from __future__ import annotations

import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from bhayanak_legends.app import create_app
from bhayanak_legends.config import SidecarConfig

AUTH = {
    "X-BL-Token": "local-sidecar-development-token-32chars",
    "Host": "127.0.0.1:23110",
}
REPO = Path(__file__).resolve().parents[2]
SHIPPED_PACK = json.loads(
    (REPO / "pack" / "findings-pack.v2.json").read_text(encoding="utf-8")
)


def build_client(tmp_path: Path, pack: dict | None = None) -> TestClient:
    pack_dir = tmp_path / "pack"
    pack_dir.mkdir(exist_ok=True)
    if pack is not None:
        (pack_dir / "findings-pack.v2.json").write_text(
            json.dumps(pack), encoding="utf-8"
        )
        source_schema = REPO / "pack" / "pack.schema.json"
        (pack_dir / "pack.schema.json").write_bytes(source_schema.read_bytes())
    config = SidecarConfig(
        port=23110,
        token="local-sidecar-development-token-32chars",
        data_dir=tmp_path / "data",
        pack_dir=pack_dir if pack is not None else tmp_path / "empty-pack",
    )
    app = create_app(config)
    generation = app.state.store.begin_owner_transition("resolving")
    app.state.test_owner_key = app.state.store.activate_owner(
        "test-puuid", "TestPlayer#1234", "sea", generation
    )
    return TestClient(app)


def seed(
    store,
    match_id: str,
    *,
    patch="16.7",
    role="MIDDLE",
    champion="Ahri",
    win=True,
    played_at="2026-01-01T00:00:00Z",
    features=None,
    duration_s=1800,
):
    store.upsert_match(
        match_id,
        played_at,
        patch,
        role,
        champion,
        win,
        duration_s,
        json.dumps(features or {}),
        owner_key=store.active_owner_key(),
    )


def test_history_summary_aggregates(tmp_path: Path):
    client = build_client(tmp_path)
    app = client.app
    seed(app.state.store, "SG2_1", win=True, role="MIDDLE")
    seed(app.state.store, "SG2_2", win=False, role="MIDDLE")
    seed(app.state.store, "SG2_3", win=True, role="BOTTOM", champion="Jinx", patch="16.6")

    with client:
        body = client.get("/history/summary", headers=AUTH).json()

    assert body["matches"] == 3
    assert body["patches"] == ["16.6", "16.7"]
    assert body["win_rate"] == pytest.approx(2 / 3)
    roles = {r["role"]: r for r in body["by_role"]}
    assert roles["MIDDLE"]["games"] == 2 and roles["MIDDLE"]["wins"] == 1
    assert roles["BOTTOM"]["games"] == 1 and roles["BOTTOM"]["wins"] == 1


def test_history_summary_sorts_patch_ranges_numerically(tmp_path: Path):
    client = build_client(tmp_path)
    store = client.app.state.store
    seed(store, "SG2_16_10", patch="16.10")
    seed(store, "SG2_16_9", patch="16.9")
    seed(store, "SG2_malformed", patch="unknown")
    seed(store, "SG2_missing", patch=None)
    with client:
        body = client.get("/history/summary", headers=AUTH).json()
        points = client.get("/progress/trajectories", headers=AUTH).json()
        aggregates = client.get("/progress/aggregates", headers=AUTH).json()

    assert body["patches"] == ["16.9", "16.10", "unknown"]
    assert [point["patch"] for point in points] == ["16.10", "16.9", "unknown"]
    assert [row["patch"] for row in aggregates] == ["16.9", "16.10", "unknown"]


def test_trajectories_rolling_window_math(tmp_path: Path):
    client = build_client(tmp_path)
    store = client.app.state.store
    outcomes = [True] * 5 + [False] * 7
    for i, win in enumerate(outcomes):
        seed(
            store,
            f"SG2_{i}",
            win=win,
            played_at=f"2026-01-{i + 1:02d}T00:00:00Z",
            champion="Ahri",
            role="MIDDLE",
            patch="16.7",
        )

    with client:
        points = client.get("/progress/trajectories", headers=AUTH).json()
        aggregates = client.get("/progress/aggregates", headers=AUTH).json()

    assert len(points) == 12
    assert [point["index"] for point in points] == list(range(12))
    assert points[0]["rolling_wr"] == 1.0
    assert points[5]["rolling_wr"] == pytest.approx(5 / 6)
    assert points[-1]["rolling_wr"] == pytest.approx(sum(outcomes[2:]) / 10)
    assert aggregates == [{"patch": "16.7", "games": 12, "wins": 5, "win_rate": 5 / 12}]


def _v2_features(**values: object) -> dict:
    features = {
        "feature_contract_version": "loltrends-parity-v2",
        "personal_history_eligibility": "eligible",
        "features": values,
        "team_state": {
            "feature": "team_gold_diff_15m",
            "feature_contract_version": "loltrends-parity-v2",
            "team_gold_diff_15m": values.get("team_gold_diff_15m"),
            "observed_through_s": 1200.0,
            "non_surrendered": True,
        },
    }
    return features


def test_postgame_latest_reads_only_nested_v2_features(tmp_path: Path):
    client = build_client(tmp_path)
    store = client.app.state.store
    seed(
        store,
        "new",
        played_at="2026-03-01T00:00:00Z",
        champion="Jinx",
        role="BOTTOM",
        win=False,
        duration_s=1500,
        features=_v2_features(
            gold_diff_10=-300.0,
            team_gold_diff_15m=-3500.0,
            cs10=55,
            level10=8,
        ),
    )

    with client:
        digest = client.get("/postgame/latest", headers=AUTH).json()

    assert digest["match_id"] == "new"
    assert digest["feature_contract_version"] == "loltrends-parity-v2"
    assert digest["features"] == {
        "gold_diff_10": -300.0,
        "team_gold_diff_15m": -3500.0,
        "cs10": 55.0,
        "level10": 8.0,
    }
    assert digest["checkpoints"] == {
        "gold_diff_10": -300.0,
        "gold_diff_15": None,
        "gold_diff_20": None,
    }
    assert digest["team_state"]["team_gold_diff_15m"] == -3500.0


def test_postgame_does_not_fallback_to_undeclared_flat_features(tmp_path: Path):
    client = build_client(tmp_path)
    seed(
        client.app.state.store,
        "undeclared-flat-row",
        features={"gold_diff_10": 120.0, "cs10": 70},
    )

    with client:
        digest = client.get("/postgame/latest", headers=AUTH).json()

    assert digest["feature_contract_version"] is None
    assert digest["features"] == {}
    assert digest["checkpoints"] == {
        "gold_diff_10": None,
        "gold_diff_15": None,
        "gold_diff_20": None,
    }
    assert digest["team_state"] is None


def test_benchmarks_are_contract_suppressed_without_v2_population_rows(tmp_path: Path):
    client = build_client(tmp_path, pack=SHIPPED_PACK)
    seed(client.app.state.store, "a1", features=_v2_features(cs10=50, level10=8))

    with client:
        body = client.get("/benchmarks", headers=AUTH).json()

    assert body == {"state": "contract-suppressed", "rows": []}


def test_what_if_without_released_model_is_suppressed(tmp_path: Path):
    client = build_client(tmp_path, pack=SHIPPED_PACK)
    seed(client.app.state.store, "a1", features=_v2_features(cs10=50, level10=8))

    with client:
        response = client.post(
            "/history/what-if",
            json={"adjustments": {"cs10": 5}},
            headers=AUTH,
        )

    assert response.status_code == 200
    assert response.json()["status"] == "suppressed"


def test_benchmarks_pack_failure_returns_503(tmp_path: Path):
    client = build_client(tmp_path, pack=None)
    with client:
        response = client.get("/benchmarks", headers=AUTH)
    assert response.status_code == 503
    assert response.json() == {"detail": "Findings Pack validation failed"}
