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
SHIPPED_PACK = json.loads((REPO / "pack" / "findings-pack.v1.json").read_text())


def build_client(tmp_path: Path, pack: dict | None = None) -> TestClient:
    pack_dir = tmp_path / "pack"
    pack_dir.mkdir(exist_ok=True)
    if pack is not None:
        (pack_dir / "findings-pack.v1.json").write_text(json.dumps(pack))
    config = SidecarConfig(
        port=23110,
        token="local-sidecar-development-token-32chars",
        data_dir=tmp_path / "data",
        pack_dir=pack_dir if pack is not None else tmp_path / "empty-pack",
    )
    return TestClient(create_app(config))


def seed(store, match_id: str, *, patch="16.7", role="MIDDLE", champion="Ahri", win=True,
         played_at="2026-01-01T00:00:00Z", features=None, duration_s=1800):
    store.upsert_match(
        match_id,
        played_at,
        patch,
        role,
        champion,
        win,
        duration_s,
        json.dumps(features or {}),
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
    assert all(set(point) == {"patch", "role", "champion", "played_at", "index", "rolling_wr"} for point in points)
    assert [point["index"] for point in points] == list(range(12))
    assert [point["played_at"] for point in points] == [
        f"2026-01-{i + 1:02d}T00:00:00Z" for i in range(12)
    ]
    first = points[0]
    assert first["rolling_wr"] == 1.0
    sixth = points[5]
    assert abs(sixth["rolling_wr"] - 5 / 6) < 1e-9
    last = points[-1]
    window = outcomes[2:]
    assert abs(last["rolling_wr"] - sum(window) / 10) < 1e-9
    assert aggregates == [{"patch": "16.7", "games": 12, "wins": 5, "win_rate": 5 / 12}]


def test_patch_aggregates_do_not_double_count_multi_role_or_champion_matches(tmp_path: Path):
    client = build_client(tmp_path)
    store = client.app.state.store
    for i in range(150):
        seed(
            store,
            f"SG2_{i}",
            patch="16.7" if i < 100 else "16.8",
            role=("TOP", "MIDDLE")[i % 2],
            champion=("Ahri", "Jinx", "Lux")[i % 3],
            win=i % 2 == 0,
            played_at=f"2026-01-{(i % 28) + 1:02d}T00:{i:02d}:00Z",
        )

    with client:
        aggregates = client.get("/progress/aggregates", headers=AUTH).json()

    assert aggregates == [
        {"patch": "16.7", "games": 100, "wins": 50, "win_rate": 0.5},
        {"patch": "16.8", "games": 50, "wins": 25, "win_rate": 0.5},
    ]


def test_trajectories_filters(tmp_path: Path):
    client = build_client(tmp_path)
    store = client.app.state.store
    for i in range(3):
        seed(store, f"A_{i}", champion="Ahri", played_at=f"2026-01-0{i + 1}T00:00:00Z")
        seed(store, f"J_{i}", champion="Jinx", role="BOTTOM")

    with client:
        ahri = client.get("/progress/trajectories", headers=AUTH, params={"champion": "Ahri"}).json()
        bottom = client.get("/progress/trajectories", headers=AUTH, params={"role": "bottom"}).json()

    assert {p["champion"] for p in ahri} == {"Ahri"}
    assert all(p["role"] == "BOTTOM" for p in bottom)


def test_postgame_latest_and_none(tmp_path: Path):
    client = build_client(tmp_path)
    with client:
        assert client.get("/postgame/latest", headers=AUTH).json() is None

    store = client.app.state.store
    seed(store, "old", played_at="2026-01-01T00:00:00Z", features={"gold_diff_10": 120.0})
    seed(
        store,
        "new",
        played_at="2026-03-01T00:00:00Z",
        champion="Jinx",
        role="BOTTOM",
        win=False,
        duration_s=1500,
        features={"gold_diff_10": -300.0, "gold_diff_15": None, "cs10": 55, "level10": 8},
    )

    with client:
        digest = client.get("/postgame/latest", headers=AUTH).json()

    assert digest["match_id"] == "new"
    assert digest["checkpoints"] == {
        "gold_diff_10": -300.0,
        "gold_diff_15": None,
        "gold_diff_20": None,
    }
    assert digest["habits"] == []
    assert "lost" in digest["headline"]


PACK = {
    **SHIPPED_PACK,
    "benchmarks": [
        {
            "role": "MIDDLE",
            "cs10_median": 64.0,
            "level10_median": 8.0,
            "gold_diff_10_median": 50.0,
            "feature_contract": {
                "cs10_median": "lane_minions_first_10m",
                "level10_median": "level10",
                "gold_diff_10_median": "gold_diff_10",
            },
            "sample": 100,
        },
    ],
}


def test_benchmarks_only_join_definition_matching_fields(tmp_path: Path):
    client = build_client(tmp_path, pack=PACK)
    store = client.app.state.store
    seed(store, "a1", features={"cs10": 50, "level10": 8, "gold_diff_10": 100.0})
    seed(store, "a2", features={"cs10": 60, "level10": 9, "gold_diff_10": 200.0})
    seed(store, "a3", features={"cs10": 70})

    with client:
        rows = client.get("/benchmarks", headers=AUTH).json()

    assert rows == [
        {
            "role": "MIDDLE",
            "personal": {"level10": 8.5, "gold_diff_10": 150.0},
            "population": {
                "level10_median": 8.0,
                "gold_diff_10_median": 50.0,
                "sample": 100,
            },
        },
    ]


def test_benchmarks_join_total_cs_only_when_pack_defines_total_cs(tmp_path: Path):
    pack = {**PACK, "benchmarks": [{**PACK["benchmarks"][0], "feature_contract": {
        **PACK["benchmarks"][0]["feature_contract"],
        "cs10_median": "cs10",
    }}]}
    client = build_client(tmp_path, pack=pack)
    seed(client.app.state.store, "a1", features={"cs10": 50})

    with client:
        rows = client.get("/benchmarks", headers=AUTH).json()

    assert rows[0]["personal"] == {"cs10": 50.0}
    assert rows[0]["population"] == {"cs10_median": 64.0, "sample": 100}



def test_benchmarks_all_roles_use_same_unit_total_cs_fixture(tmp_path: Path):
    roles = ("TOP", "JUNGLE", "MIDDLE", "BOTTOM", "UTILITY")
    pack = {
        **PACK,
        "benchmarks": [
            {
                "role": role,
                "cs10_median": 60.0,
                "feature_contract": {"cs10_median": "cs10"},
                "sample": 100,
            }
            for role in roles
        ],
    }
    client = build_client(tmp_path, pack=pack)
    for index, role in enumerate(roles):
        seed(client.app.state.store, f"match-{role}", role=role, features={"cs10": 50 + index})

    with client:
        rows = client.get("/benchmarks", headers=AUTH).json()

    assert {row["role"] for row in rows} == set(roles)
    assert all(set(row["personal"]) == {"cs10"} for row in rows)
    assert all(set(row["population"]) == {"cs10_median", "sample"} for row in rows)

def test_benchmarks_empty_when_pack_missing(tmp_path: Path):
    client = build_client(tmp_path, pack=None)
    with client:
        assert client.get("/benchmarks", headers=AUTH).json() == []
