from __future__ import annotations

import json
from pathlib import Path

from fastapi.testclient import TestClient

from bhayanak_legends.app import create_app
from bhayanak_legends.config import SidecarConfig

AUTH = {
    "X-BL-Token": "local-sidecar-development-token-32chars",
    "Host": "127.0.0.1:23110",
}


def build_client(tmp_path: Path) -> TestClient:
    config = SidecarConfig(
        port=23110,
        token=AUTH["X-BL-Token"],
        data_dir=tmp_path / "data",
        pack_dir=tmp_path / "empty-pack",
    )
    return TestClient(create_app(config))


def seed(store, match_id: str, *, owner_key: str, champion: str = "Ahri", role: str = "MIDDLE", win: bool = True) -> None:
    store.upsert_match(
        match_id,
        "2026-01-01T00:00:00Z",
        "16.7",
        role,
        champion,
        win,
        1800,
        json.dumps({}),
        owner_key=owner_key,
    )


def test_history_insights_requires_authentication_and_reads_only_active_owner(tmp_path: Path) -> None:
    client = build_client(tmp_path)
    store = client.app.state.store
    owner_a = store.owner_key_for_puuid("puuid-a")
    owner_b = store.owner_key_for_puuid("puuid-b")
    generation = store.begin_owner_transition("resolving")
    store.activate_owner("puuid-a", "PlayerA#TAG", "sea", generation)
    for index in range(6):
        seed(store, f"a-{index}", owner_key=owner_a, win=index % 2 == 0)
    seed(store, "b-0", owner_key=owner_b, champion="Jinx", role="BOTTOM")

    with client:
        assert client.get("/history/insights", headers={"Host": AUTH["Host"]}).status_code == 401
        response = client.get(
            "/history/insights",
            headers=AUTH,
            params={"role": "middle", "champion": "Ahri"},
        )

    assert response.status_code == 200
    body = response.json()
    assert body["sample_size"] == 6
    assert body["filters"] == {"role": "MIDDLE", "champion": "Ahri"}
    assert body["roles"] == [
        {
            "role": "MIDDLE",
            "games": 6,
            "wins": 3,
            "win_rate": 0.5,
            "sample_status": "review",
        }
    ]
    assert body["champions"][0]["champion"] == "Ahri"
    assert body["champions"][0]["roles"] == ["MIDDLE"]
    assert body["windows"]["latest"]["games"] == 6
    assert body["windows"]["preceding"]["completeness"] == "unavailable"
