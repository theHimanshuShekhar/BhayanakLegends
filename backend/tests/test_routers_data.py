import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from bhayanak_legends.app import create_app
from bhayanak_legends.config import SidecarConfig

AUTH = {"X-BL-Token": "dev"}
REPO = Path(__file__).resolve().parents[3]


def build_client(tmp_path: Path, pack: dict | None = None) -> TestClient:
    pack_dir = tmp_path / "pack"
    pack_dir.mkdir(exist_ok=True)
    if pack is not None:
        (pack_dir / "findings-pack.v1.json").write_text(json.dumps(pack))
    config = SidecarConfig(
        port=23110,
        token="dev",
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

    assert body["patches"] == ["16.9", "16.10", "unknown"]
    assert [point["patch"] for point in points] == ["16.9", "16.10", "unknown"]


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

    assert len(points) == 12
    first = points[0]
    assert (first["games"], first["wins"], first["rolling_wr"]) == (1, 1, 1.0)
    sixth = points[5]
    assert sixth["games"] == 6 and sixth["wins"] == 5
    assert abs(sixth["rolling_wr"] - 5 / 6) < 1e-9
    last = points[-1]
    window = outcomes[2:]
    assert last["games"] == 10
    assert last["wins"] == sum(window)
    assert abs(last["rolling_wr"] - sum(window) / 10) < 1e-9


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
    habit_keys = {h["key"] for h in digest["habits"]}
    assert habit_keys == {
        "recall_safety",
        "fast_first_dragon",
        "spend_before_backing",
        "plates_by_14",
    }
    assert all(h["verdict"] == "n/a" for h in digest["habits"])
    assert "lost" in digest["headline"]


PACK = {
    "schema_version": 1,
    "benchmarks": [
        {"role": "MIDDLE", "cs10_median": 64.0, "level10_median": None, "gold10_median": None, "sample": 100},
    ],
}


def test_benchmarks_joins_pack_with_personal_medians(tmp_path: Path):
    client = build_client(tmp_path, pack=PACK)
    store = client.app.state.store
    seed(store, "a1", features={"cs10": 50, "level10": 8, "gold_diff_10": 100.0})
    seed(store, "a2", features={"cs10": 60, "level10": 9, "gold_diff_10": 200.0})
    seed(store, "a3", features={"cs10": 70})

    with client:
        rows = client.get("/benchmarks", headers=AUTH).json()

    middle = next(r for r in rows if r["role"] == "MIDDLE")
    assert middle["personal"]["cs10"] == 60.0
    assert middle["personal"]["level10"] == 8.5
    assert middle["personal"]["gold10"] == 150.0
    assert middle["population"]["cs10_median"] == 64.0
    assert middle["population"]["sample"] == 100


def test_benchmarks_empty_when_pack_missing(tmp_path: Path):
    client = build_client(tmp_path, pack=None)
    with client:
        assert client.get("/benchmarks", headers=AUTH).json() == []
