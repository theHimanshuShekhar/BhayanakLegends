"""LCU bridge tests: pure parsers plus fixture-driven transport injection.

No League client exists on this box; every scenario replays the fixtures under
tests/fixtures/lcu/ through fake transports exactly the way the production
HttpxLcuConnection / HttpxIngameTransport behave on Windows.
"""

import asyncio
import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from bhayanak_legends.app import create_app
from bhayanak_legends.config import SidecarConfig
import bhayanak_legends.lcu as lcu_module
from bhayanak_legends.lcu import (
    ChampionDirectory,
    HttpxIngameTransport,
    HttpxLcuConnection,
    champion_map_from_ddragon,
    find_lockfile,
    lockfile_candidates,
    parse_lockfile,
)
from bhayanak_legends.live import (
    ChampSelectSnapshot,
    InGameSnapshot,
    LiveService,
    build_champ_select_snapshot,
    build_ingame_snapshot,
)
from bhayanak_legends.sse import Hub

FIXTURES = Path(__file__).parent / "fixtures" / "lcu"

CHAMPION_NAMES = {
    1: "Annie",
    25: "Miss Fortune",
    22: "Lucian",
    34: "Amumu",
    238: "Camille",
    498: "Xayah",
}


def load_json(name: str):
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


GAMEFLOW_PHASES = [
    line.strip()
    for line in (FIXTURES / "gameflow_phases.txt").read_text(encoding="utf-8").splitlines()
    if line.strip()
]


class FakeLcuTransport:
    """Replays the scripted gameflow phase sequence one call at a time."""

    def __init__(self, phases: list[str], session_payload: dict | None = None):
        self._phases = list(phases)
        self._session = session_payload
        self.phase_calls = 0
        self.session_calls = 0

    async def gameflow_phase(self) -> str | None:
        index = min(self.phase_calls, len(self._phases) - 1)
        self.phase_calls += 1
        return self._phases[index]

    async def champ_select_session(self) -> dict | None:
        self.session_calls += 1
        return self._session

    async def current_summoner(self) -> dict | None:
        return {}


class FakeIngameTransport:
    def __init__(self, payloads: list[dict | None]):
        self._payloads = list(payloads)
        self.calls = 0

    async def allgamedata(self) -> dict | None:
        index = min(self.calls, len(self._payloads) - 1)
        self.calls += 1
        return self._payloads[index]


def drain(queue: asyncio.Queue) -> list[dict]:
    frames = []
    while True:
        try:
            raw = queue.get_nowait()
        except asyncio.QueueEmpty:
            return frames
        frames.append(json.loads(str(raw).removeprefix("data: ")))


# ---------------------------------------------------------------- lockfile


def test_parse_lockfile_documented_shape():
    info = parse_lockfile((FIXTURES / "lockfile.txt").read_text(encoding="utf-8"))
    assert info.port == 63569
    assert info.token == "secret"
    assert info.protocol == "https"


@pytest.mark.parametrize(
    "text",
    [
        "LeagueClient:63569:secret:https",
        "LeagueClient:13268:notaport:secret:https",
        "LeagueClient:notapid:63569:secret:https",
        "LeagueClient:13268:63569::https",
        "LeagueClient:13268:63569:secret:",
        "LeagueClient:13268:63569:secret:https:extra",
    ],
)
def test_parse_lockfile_rejects_malformed_shapes(text):
    with pytest.raises(ValueError):
        parse_lockfile(text)


async def test_httpx_lcu_connection_uses_lockfile_fields_for_gameflow_request(
    tmp_path, monkeypatch
):
    lockfile = tmp_path / "lockfile"
    lockfile.write_text("LeagueClient:13268:63569:secret:http", encoding="utf-8")
    monkeypatch.setattr(lcu_module, "find_lockfile", lambda: lockfile)

    class FakeResponse:
        def json(self):
            return "ChampSelect"
        def raise_for_status(self):
            return None

    class FakeAsyncClient:
        instances = []

        def __init__(self, **kwargs):
            self.kwargs = kwargs
            self.paths = []
            self.__class__.instances.append(self)

        async def get(self, path):
            self.paths.append(path)
            return FakeResponse()

    monkeypatch.setattr(lcu_module.httpx, "AsyncClient", FakeAsyncClient)

    connection = HttpxLcuConnection()
    assert await connection.gameflow_phase() == "ChampSelect"
    client = FakeAsyncClient.instances[0]
    assert str(client.kwargs["base_url"]) == "http://127.0.0.1:63569"
    assert client.kwargs["auth"] == ("riot", "secret")
    assert client.paths == ["/lol-gameflow/v1/gameflow-phase"]

async def test_httpx_lcu_connection_accepts_explicit_lockfile_path(tmp_path, monkeypatch):
    lockfile = tmp_path / "fake.lockfile"
    lockfile.write_text("Fake:123:23456:fake-token:http", encoding="utf-8")

    class FakeResponse:
        def json(self):
            return "InProgress"

        def raise_for_status(self):
            return None

    class FakeAsyncClient:
        def __init__(self, **kwargs):
            self.kwargs = kwargs

        async def get(self, path):
            return FakeResponse()

    monkeypatch.setattr(lcu_module.httpx, "AsyncClient", FakeAsyncClient)
    connection = HttpxLcuConnection(lockfile_path=lockfile)

    assert await connection.gameflow_phase() == "InProgress"


def test_replay_transport_settings_are_env_overridable(monkeypatch, tmp_path):
    lockfile = tmp_path / "fake.lockfile"
    lockfile.write_text("Fake:123:23456:fake-token:http", encoding="utf-8")
    monkeypatch.setenv("BHAYANAK_LCU_LOCKFILE", str(lockfile))
    monkeypatch.setenv("BHAYANAK_LIVE_CLIENT_DATA_URL", "http://127.0.0.1:23457/allgamedata")

    config = SidecarConfig()

    assert config.lcu_lockfile == lockfile
    assert config.live_client_data_url.endswith(":23457/allgamedata")

def test_lockfile_candidates_cover_windows_and_wsl(monkeypatch):
    monkeypatch.setenv("LOCALAPPDATA", "/w/AppData/Local")
    candidates = lockfile_candidates()
    assert candidates[0] == Path("/w/AppData/Local/Riot Games/League of Legends/lockfile")
    assert Path("C:/Riot Games/League of Legends/lockfile") in candidates
    assert Path("/mnt/c/Riot Games/League of Legends/lockfile") in candidates


def test_find_lockfile_picks_first_existing(tmp_path):
    missing = tmp_path / "missing.lockfile"
    present = tmp_path / "present.lockfile"
    present.write_text("LeagueClient:13268:63569:secret:https", encoding="utf-8")
    assert find_lockfile([missing, present]) == present
    assert find_lockfile([missing]) is None


# ------------------------------------------------------------ data dragon


def test_champion_map_from_ddragon_payload():
    payload = {
        "type": "champion",
        "data": {
            "Annie": {"key": "1", "name": "Annie"},
            "MissFortune": {"key": "25", "name": "Miss Fortune"},
            "Fiddlesticks": {"key": "9", "name": "Fiddlesticks"},
            "Broken": {"key": "x", "name": "Ignored"},
        },
    }
    assert champion_map_from_ddragon(payload) == {
        1: "Annie",
        25: "Miss Fortune",
        9: "Fiddlesticks",
    }


def _ddragon_champions_payload() -> dict:
    return {
        "data": {
            "Annie": {"key": "1", "name": "Annie"},
            "MissFortune": {"key": "25", "name": "Miss Fortune"},
        }
    }


async def test_champion_directory_fetches_then_serves_fresh_disk_cache(tmp_path):
    calls: list[str] = []

    async def versions() -> list[str]:
        calls.append("versions")
        return ["16.16.1", "14.17.1"]

    async def champions(version: str) -> dict:
        calls.append(f"champions:{version}")
        return _ddragon_champions_payload()

    first = ChampionDirectory(
        tmp_path / "data", fetch_versions=versions, fetch_champions=champions, clock=lambda: 1_000
    )
    assert await first.get() == {1: "Annie", 25: "Miss Fortune"}
    assert calls == ["versions", "champions:16.16.1"]
    assert (tmp_path / "data" / "ddragon.json").is_file()

    async def must_not_touch_network(*_a) -> dict:
        raise AssertionError("network hit despite fresh disk cache")

    second = ChampionDirectory(
        tmp_path / "data",
        fetch_versions=must_not_touch_network,
        fetch_champions=must_not_touch_network,
        clock=lambda: 1_000 + 3_600,
    )
    assert await second.get() == {1: "Annie", 25: "Miss Fortune"}
    assert await second.get() == {1: "Annie", 25: "Miss Fortune"}  # memory cache


async def test_champion_directory_failure_degrades_gracefully(tmp_path):
    async def boom(*_a):
        raise OSError("offline")

    empty = ChampionDirectory(tmp_path / "none", fetch_versions=boom, fetch_champions=boom)
    assert await empty.get() == {}

    seed = ChampionDirectory(
        tmp_path / "data",
        fetch_versions=lambda: _slow_ok(),
        fetch_champions=lambda version: _slow_champs(version),
        clock=lambda: 1_000,
    )
    assert await seed.get() == {1: "Annie", 25: "Miss Fortune"}

    stale_but_usable = ChampionDirectory(
        tmp_path / "data", fetch_versions=boom, fetch_champions=boom, clock=lambda: 1_000 + 90_000
    )
    assert await stale_but_usable.get() == {1: "Annie", 25: "Miss Fortune"}  # stale disk beats empty


async def _slow_ok() -> list[str]:
    return ["16.16.1"]


async def _slow_champs(_version: str) -> dict:
    return _ddragon_champions_payload()


# ------------------------------------------------------- pure snapshot builders


def test_build_champ_select_snapshot_strips_enemy_names_and_maps_bans():
    session = load_json("champselect_session.json")
    snapshot = build_champ_select_snapshot(session, "ChampSelect", CHAMPION_NAMES)

    assert snapshot.active is True
    assert snapshot.phase == "ChampSelect"
    assert snapshot.timer_sec == 23

    assert [(b.champion_id, b.name) for b in snapshot.bans_ally] == [
        (25, "Miss Fortune"),
        (1, "Annie"),
    ]
    # unmapped champion ids keep name=None so the UI renders "Champion {id}"
    assert [(b.champion_id, b.name) for b in snapshot.bans_enemy] == [(412, None), (60, None)]

    local = next(cell for cell in snapshot.ally if cell.is_local)
    assert (local.cell_id, local.champion_id, local.champion, local.name, local.state) == (
        2, 1, "Annie", "SacredButtholio", "picked",
    )
    assert [cell.state for cell in snapshot.ally] == ["picked", "intent", "picked", "none", "picked"]

    # COMPLIANCE: theirTeam summoner names are dropped at the service layer.
    assert all(cell.name is None for cell in snapshot.enemy)
    assert [(c.champion_id, c.champion) for c in snapshot.enemy] == [
        (238, "Camille"),
        (999, None),  # unmapped → UI renders "Champion 999"
        (0, None),
        (0, None),
        (22, "Lucian"),
    ]
    assert [cell.state for cell in snapshot.enemy] == ["picked", "picked", "intent", "none", "picked"]
    assert "HiddenEnemy" not in json.dumps(snapshot.model_dump())


def test_build_ingame_snapshot_maps_players_scores_items_events():
    snapshot, game_id = build_ingame_snapshot(load_json("allgamedata.json"))

    assert game_id == 5123456789
    assert snapshot.active is True
    assert snapshot.clock_s == pytest.approx(754.32)
    assert snapshot.mode == "CLASSIC"
    assert snapshot.local_summoner == "SacredButtholio"
    assert snapshot.local_champion == "Viktor"

    order, chaos = snapshot.teams["order"], snapshot.teams["chaos"]
    assert len(order) == 5 and len(chaos) == 5

    me = next(p for p in order if p.summoner == "SacredButtholio")
    assert (me.champion, me.level, me.kills, me.deaths, me.assists) == ("Viktor", 12, 4, 2, 7)
    assert me.cs == 213  # scores.creepScore
    assert me.ward_score == pytest.approx(1.42)  # scores.wardScore
    assert [(i.id, i.count) for i in me.items] == [(3157, 1), (1056, 1), (2003, 2)]  # slot order, itemID!=0

    dragon = [e for e in snapshot.events if e.name == "DragonKill"]
    assert len(dragon) == 1
    assert dragon[0].detail == "Infernal"
    assert dragon[0].t_s == pytest.approx(612.9)

    kill = next(e for e in snapshot.events if e.name == "ChampionKill")
    assert (kill.actor, kill.victim) == ("SacredButtholio", "EnemyADC")

    assert [e.name for e in snapshot.events][0] == "GameStart"  # newest last
    assert [e.t_s for e in snapshot.events] == sorted(e.t_s for e in snapshot.events)


# ------------------------------------------------------------ service loop


def _service(phases: list[str], hub: Hub, session_payload=None, game_payloads=None):
    lcu = FakeLcuTransport(phases, session_payload=session_payload)
    ingame = FakeIngameTransport(game_payloads if game_payloads is not None else [None])
    service = LiveService(
        lcu,
        ingame,
        hub,
        poll_interval=0.01,
        champion_names=CHAMPION_NAMES,
    )
    return service, lcu, ingame


async def test_idle_tick_publishes_idle_frames_and_coarse_status():
    hub = Hub()
    queue = hub.subscribe()
    service, _lcu, _ig = _service(["None"], hub)

    await service.tick()

    types = [frame["type"] for frame in drain(queue)]
    assert types == ["champselect.state", "live.state", "live.status"]
    assert service.session()["active"] is False
    assert service.ingame()["active"] is False
    assert service.status()["champ_select"]["active"] is False
    assert service.status()["last_error"] is None


async def test_idle_then_champ_select_then_in_game_transitions():
    hub = Hub()
    queue = hub.subscribe()
    service, lcu, ingame = _service(
        GAMEFLOW_PHASES[:4],  # None → Lobby → Matchmaking → ChampSelect
        hub,
        session_payload=load_json("champselect_session.json"),
    )

    await service.tick()  # None: idle
    await service.tick()  # Lobby: still idle everywhere, no changes
    await service.tick()  # Matchmaking: still idle, no changes
    frames_after_idle = drain(queue)
    assert [f["type"] for f in frames_after_idle] == ["champselect.state", "live.state", "live.status"]

    await service.tick()  # ChampSelect with session
    champ_frame, status_frame = drain(queue)
    assert champ_frame["type"] == "champselect.state"
    assert status_frame["type"] == "live.status"
    snap = champ_frame["data"]
    assert snap["phase"] == "ChampSelect"
    assert snap["timer_sec"] == 23
    assert any(c["is_local"] and c["name"] == "SacredButtholio" for c in snap["ally"])
    assert "HiddenEnemy" not in json.dumps(snap)
    assert status_frame["data"]["champ_select"]["active"] is True
    assert lcu.session_calls == 1
    assert ingame.calls == 0  # :2999 untouched while drafting


async def test_in_game_window_polls_allgamedata_and_publishes_rich_state():
    hub = Hub()
    queue = hub.subscribe()
    game = load_json("allgamedata.json")
    service, _lcu, ingame = _service(
        ["ChampSelect", "GameStart", "InProgress"],
        hub,
        session_payload=load_json("champselect_session.json"),
        game_payloads=[game],
    )

    await service.tick()  # ChampSelect
    drain(queue)
    await service.tick()  # GameStart → in-game window opens
    frames = drain(queue)
    types = [f["type"] for f in frames]

    assert types.count("live.state") == 1
    assert types.count("champselect.state") == 1  # back to idle
    live_state = next(f["data"] for f in frames if f["type"] == "live.state")
    assert live_state["active"] is True
    assert live_state["mode"] == "CLASSIC"
    assert live_state["local_summoner"] == "SacredButtholio"
    assert live_state["local_champion"] == "Viktor"
    assert len(live_state["teams"]["order"]) == 5
    assert any(e["name"] == "DragonKill" and e["detail"] == "Infernal" for e in live_state["events"])
    status = next(f["data"] for f in frames if f["type"] == "live.status")
    assert status["ingame"]["active"] is True
    assert status["ingame"]["clock_s"] == 754
    assert status["ingame"]["game_id"] == 5123456789
    assert ingame.calls == 1

    await service.tick()  # InProgress, identical payload → nothing changes
    assert drain(queue) == []


async def test_service_accessors_return_idle_snapshots_before_first_tick():
    hub = Hub()
    service, _lcu, _ig = _service(["None"], hub)
    assert service.session() == ChampSelectSnapshot().model_dump()
    assert service.ingame() == InGameSnapshot().model_dump()


async def test_transport_errors_surface_as_last_error_not_crash():
    class ExplodingLcu:
        async def gameflow_phase(self):
            raise RuntimeError("boom")

    class QuietIngame:
        async def allgamedata(self):
            return None

    hub = Hub()
    queue = hub.subscribe()
    service = LiveService(ExplodingLcu(), QuietIngame(), hub, poll_interval=0.01)
    await service.tick()

    frames = drain(queue)
    status = next(f["data"] for f in frames if f["type"] == "live.status")
    assert status["last_error"] == "boom"
    assert status["champ_select"]["active"] is False


# --------------------------------------------------------------- app wiring


class StubLiveService:
    """Stands in for LiveService to prove app.py wires the new endpoints."""

    def __init__(self, *args, **kwargs):
        pass

    async def start(self):
        pass

    async def stop(self):
        pass

    def session(self):
        return {
            "active": True,
            "phase": "ChampSelect",
            "timer_sec": 23,
            "bans_ally": [{"champion_id": 25, "name": "Miss Fortune"}],
            "bans_enemy": [{"champion_id": 412, "name": None}],
            "ally": [],
            "enemy": [],
        }

    def ingame(self):
        return {
            "active": True,
            "clock_s": 754.32,
            "mode": "CLASSIC",
            "local_summoner": "SacredButtholio",
            "local_champion": "Viktor",
            "teams": {"order": [], "chaos": []},
            "events": [],
        }

    def status(self):
        return {
            "champ_select": {"active": False, "phase": None},
            "ingame": {"active": True, "game_id": 5123456789, "mode": "CLASSIC", "clock_s": 754},
            "last_error": None,
        }


AUTH = {"X-BL-Token": "test-token-123"}


def _client(tmp_path: Path):
    config = SidecarConfig(port=23110, token="test-token-123", data_dir=tmp_path / "data", pack_dir=None)
    repo_pack = Path(__file__).resolve().parents[2] / "pack"
    if repo_pack.exists():
        config.pack_dir = repo_pack
    return TestClient(create_app(config))


def test_live_endpoints_idle_by_default(tmp_path):
    with _client(tmp_path) as client:
        res_session = client.get("/live/session", headers=AUTH)
        res_ingame = client.get("/live/ingame", headers=AUTH)
        res_status = client.get("/live/status", headers=AUTH)

    assert res_session.status_code == 200
    assert res_session.json() == {
        "active": False,
        "phase": None,
        "timer_sec": None,
        "bans_ally": [],
        "bans_enemy": [],
        "ally": [],
        "enemy": [],
    }
    assert res_ingame.status_code == 200
    body = res_ingame.json()
    assert body["active"] is False and body["teams"] == {"order": [], "chaos": []}
    assert res_status.status_code == 200


def test_live_endpoints_expose_service_snapshots(tmp_path, monkeypatch):
    import bhayanak_legends.live as live_module

    monkeypatch.setattr(live_module, "LiveService", StubLiveService)
    with _client(tmp_path) as client:
        session = client.get("/live/session", headers=AUTH).json()
        ingame = client.get("/live/ingame", headers=AUTH).json()
        status = client.get("/live/status", headers=AUTH).json()

    assert session["active"] is True and session["timer_sec"] == 23
    assert session["bans_ally"][0]["name"] == "Miss Fortune"
    assert ingame["local_champion"] == "Viktor"
    assert status["ingame"]["game_id"] == 5123456789


def test_production_transports_are_constructible():
    conn = HttpxLcuConnection()
    assert conn._client is None  # lazily built once the lockfile appears
    assert HttpxIngameTransport() is not None
