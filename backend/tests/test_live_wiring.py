from __future__ import annotations

from copy import deepcopy
from contextlib import nullcontext
import json
from pathlib import Path
from types import SimpleNamespace
import time

import pytest
from fastapi.testclient import TestClient

import bhayanak_legends.live as live_module
from bhayanak_legends.app import create_app
from bhayanak_legends.config import SidecarConfig
from bhayanak_legends.credentials import InMemoryCredentialStore

from bhayanak_legends.inference import InferenceRuntime
from bhayanak_legends.lcu import DataDragonCatalogProvider
from bhayanak_legends.live import LiveService
from bhayanak_legends.live_features import (
    FEATURE_ORDER,
    LIVE_WP_CONTRACT_VERSION,
    DataDragonCatalog,
    LiveWpFeatureProvider,
)
from bhayanak_legends.models import LiveInference
from bhayanak_legends.sse import Hub


FIXTURE = Path(__file__).parent / "fixtures" / "live_wp_v2_parity.json"


def load_fixture() -> dict:
    return json.loads(FIXTURE.read_text(encoding="utf-8"))


class StaticCatalogProvider:
    def __init__(self, catalog: DataDragonCatalog | None) -> None:
        self.catalog = catalog
        self.patches: list[str] = []

    async def get(self, patch: str) -> DataDragonCatalog | None:
        self.patches.append(patch)
        return self.catalog


class MissingCatalogProvider:
    async def get(self, patch: str) -> DataDragonCatalog | None:
        return None


class FixtureLcu:
    async def gameflow_phase(self) -> str:
        return "InProgress"

    async def champ_select_session(self):
        return None


class FixtureIngame:
    def __init__(self, payload: dict) -> None:
        self.payload = payload

    async def allgamedata(self) -> dict:
        return self.payload


class RecordingRuntime:
    def __init__(self) -> None:
        self.vector = None

    def predict_live_snapshot(self, snapshot, *, observed_game_time_s, feature_provider):
        self.vector = feature_provider(snapshot)
        if self.vector is None:
            return LiveInference(
                status="suppressed",
                observed_game_time_s=observed_game_time_s,
                reason="live feature vector unavailable",
            )
        return LiveInference(
            status="available",
            probability=0.73,
            observed_game_time_s=observed_game_time_s,
            model_version="fixture-live-v1",
            pack_version="fixture-pack-v1",
        )


def catalog(fixture: dict) -> DataDragonCatalog:
    return DataDragonCatalog(
        fixture["data_dragon_version"],
        {int(item_id): float(cost) for item_id, cost in fixture["data_dragon_items"].items()},
    )


async def test_catalog_provider_fetches_only_the_requested_patch_and_caches_success() -> None:
    calls: list[tuple[str, str | None]] = []

    async def versions() -> list[str]:
        calls.append(("versions", None))
        return ["16.18.1", "16.17.1"]

    async def items(version: str) -> dict:
        calls.append(("items", version))
        return {"data": {"1001": {"gold": {"total": 300}}}}

    provider = DataDragonCatalogProvider(fetch_versions=versions, fetch_items=items)

    resolved = await provider.get("16.17.791.1234")
    cached = await provider.get("16.17")

    assert resolved is not None
    assert cached is resolved
    assert resolved.version == "16.17.1"
    assert resolved.cost(1001) == 300
    assert calls == [("versions", None), ("items", "16.17.1")]

    assert await provider.get("16.19") is None
    assert calls == [("versions", None), ("items", "16.17.1"), ("versions", None)]


async def test_catalog_provider_suppresses_when_no_matching_version_exists() -> None:
    item_calls: list[str] = []

    async def items(version: str) -> dict:
        item_calls.append(version)
        return {"data": {"1001": {"gold": {"total": 300}}}}

    provider = DataDragonCatalogProvider(
        fetch_versions=lambda: _versions_only("16.18.1"),
        fetch_items=items,
    )

    assert await provider.get("16.17") is None
    assert item_calls == []


async def test_live_service_passes_exact_adapter_to_runtime() -> None:
    fixture = load_fixture()
    snapshot = deepcopy(fixture["observations"][0]["live"])
    snapshot["observed_at_s"] = time.time()
    snapshot["gameData"]["gameVersion"] = fixture["patch"]
    snapshot["activePlayer"]["summonerName"] = "FixturePlayer01"
    runtime = RecordingRuntime()
    service = LiveService(
        FixtureLcu(),
        FixtureIngame(snapshot),
        Hub(),
        inference=runtime,
        feature_provider=LiveWpFeatureProvider(StaticCatalogProvider(catalog(fixture))),
    )

    await service.tick()

    body = service.ingame()
    assert body["inference"]["status"] == "available"
    assert body["inference"]["probability"] == pytest.approx(0.73)
    assert body["inference"]["model_version"] == "fixture-live-v1"
    assert body["inference"]["pack_version"] == "fixture-pack-v1"
    assert runtime.vector is not None
    assert runtime.vector.contract_version == LIVE_WP_CONTRACT_VERSION
    assert runtime.vector.values == pytest.approx(fixture["observations"][0]["expected"]["100"])


async def test_live_service_truthfully_suppresses_missing_catalog() -> None:
    fixture = load_fixture()
    snapshot = deepcopy(fixture["observations"][0]["live"])
    snapshot["observed_at_s"] = time.time()
    snapshot["gameData"]["gameVersion"] = fixture["patch"]
    runtime = RecordingRuntime()
    service = LiveService(
        FixtureLcu(),
        FixtureIngame(snapshot),
        Hub(),
        inference=runtime,
        feature_provider=LiveWpFeatureProvider(MissingCatalogProvider()),
    )

    await service.tick()

    inference = service.ingame()["inference"]
    assert inference["status"] == "suppressed"
    assert inference["probability"] is None
    assert "Data Dragon" in inference["reason"]
    assert runtime.vector is None


async def test_live_service_refreshes_discovered_patch_for_each_game_lifecycle() -> None:
    fixture = load_fixture()
    first = deepcopy(fixture["observations"][0]["live"])
    first["gameData"].update({"gameId": 1001, "gameVersion": None})
    second = deepcopy(fixture["observations"][0]["live"])
    second["gameData"].update({"gameId": 1002, "gameVersion": None})

    class LifecycleLcu:
        def __init__(self) -> None:
            self.phases = iter(["InProgress", "EndOfGame", "InProgress"])
            self.versions = iter(["15.18.1", "16.17.1"])
            self.version_calls = 0

        async def gameflow_phase(self) -> str:
            return next(self.phases)

        async def champ_select_session(self):
            return None

        async def client_version(self) -> str:
            self.version_calls += 1
            return next(self.versions)

    class LifecycleIngame:
        def __init__(self) -> None:
            self.games = iter([first, second])

        async def allgamedata(self) -> dict:
            return next(self.games)

    class RecordingProvider:
        def __init__(self) -> None:
            self.patches: list[str | None] = []
            self.last_reason = "fixture suppression"

        async def prepare(self, _raw_game, **kwargs):
            self.patches.append(kwargs.get("patch"))
            return None

    lcu = LifecycleLcu()
    provider = RecordingProvider()
    service = LiveService(
        lcu,
        LifecycleIngame(),
        Hub(),
        inference=RecordingRuntime(),
        feature_provider=provider,
    )

    await service.tick()
    await service.tick()
    assert service._discovered_patch is None
    await service.tick()

    assert provider.patches == ["15.18.1", "16.17.1"]
    assert lcu.version_calls == 2


async def test_live_service_configured_patch_stays_stable_across_games() -> None:
    fixture = load_fixture()
    first = deepcopy(fixture["observations"][0]["live"])
    first["gameData"].update({"gameId": 1001, "gameVersion": None})
    second = deepcopy(fixture["observations"][0]["live"])
    second["gameData"].update({"gameId": 1002, "gameVersion": None})

    class ConfiguredLcu:
        def __init__(self) -> None:
            self.version_calls = 0

        async def gameflow_phase(self) -> str:
            return "InProgress"

        async def champ_select_session(self):
            return None

        async def client_version(self) -> str:
            self.version_calls += 1
            return "16.17.1"

    class TwoGames:
        def __init__(self) -> None:
            self.games = iter([first, second])

        async def allgamedata(self) -> dict:
            return next(self.games)

    class RecordingProvider:
        def __init__(self) -> None:
            self.patches: list[str | None] = []
            self.last_reason = "fixture suppression"

        async def prepare(self, _raw_game, **kwargs):
            self.patches.append(kwargs.get("patch"))
            return None

    lcu = ConfiguredLcu()
    provider = RecordingProvider()
    service = LiveService(
        lcu,
        TwoGames(),
        Hub(),
        inference=RecordingRuntime(),
        feature_provider=provider,
        trusted_patch="15.18.9",
    )

    await service.tick()
    await service.tick()

    assert provider.patches == ["15.18.9", "15.18.9"]
    assert lcu.version_calls == 0
async def test_live_provider_accepts_official_shape_without_source_capture() -> None:
    fixture = load_fixture()
    snapshot = deepcopy(fixture["observations"][0]["live"])
    snapshot["gameData"]["gameVersion"] = fixture["patch"]
    provider = LiveWpFeatureProvider(StaticCatalogProvider(catalog(fixture)))
    adapter = await provider.prepare(snapshot, monotonic_s=100.0)
    assert adapter is not None
    assert adapter(snapshot) is not None

async def test_live_provider_accepts_official_shape_with_trusted_patch_provider() -> None:
    fixture = load_fixture()
    snapshot = deepcopy(fixture["observations"][0]["live"])
    snapshot["observed_at_s"] = 100.0
    snapshot["activePlayer"]["summonerName"] = "FixturePlayer01"
    snapshot["gameData"].pop("gameVersion", None)
    provider = LiveWpFeatureProvider(
        StaticCatalogProvider(catalog(fixture)),
        patch_provider=lambda _snapshot: fixture["patch"],
    )
    adapter = await provider.prepare(snapshot, now_s=100.0)
    assert adapter is not None
    assert adapter(snapshot) is not None

async def test_live_provider_marks_identical_observation_stale_after_monotonic_bound() -> None:
    fixture = load_fixture()
    snapshot = deepcopy(fixture["observations"][0]["live"])
    snapshot["gameData"]["gameVersion"] = fixture["patch"]
    provider = LiveWpFeatureProvider(
        StaticCatalogProvider(catalog(fixture)),
        monotonic_clock=lambda: 0.0,
    )
    assert await provider.prepare(snapshot, monotonic_s=0.0) is not None
    assert await provider.prepare(snapshot, monotonic_s=5.001) is None
    assert provider.last_reason == "live observation stream is stale"




async def test_typed_live_vector_reaches_runtime_model_session() -> None:
    fixture = load_fixture()
    snapshot = deepcopy(fixture["observations"][0]["live"])
    snapshot["gameData"]["gameVersion"] = fixture["patch"]
    feature_provider = LiveWpFeatureProvider(StaticCatalogProvider(catalog(fixture)))
    adapter = await feature_provider.prepare(snapshot, observed_at_s=1.0, now_s=1.0)
    assert adapter is not None

    bounds = SimpleNamespace(min=-1_000_000.0, max=1_000_000.0)
    card = SimpleNamespace(
        feature_order=list(FEATURE_ORDER),
        features=[SimpleNamespace(name=name, bounds=bounds) for name in FEATURE_ORDER],
        patch_scope=SimpleNamespace(min="14.17", max="16.17"),
        input_names=["features"],
        output_names=["probability"],
        preprocessing=[],
        model_version="fixture-live-v1",
    )
    declaration = SimpleNamespace(model_card=card, artifact=SimpleNamespace(path="model.onnx"))
    pack = SimpleNamespace(pack_version="fixture-pack-v1")

    class Session:
        def run(self, output_names, inputs):
            assert output_names == ["probability"]
            assert len(inputs["features"]) == 1
            return [[0.73]]

    runtime = InferenceRuntime.__new__(InferenceRuntime)
    runtime._pack_store = SimpleNamespace(pack_dir=Path("."), read_transaction=nullcontext)
    runtime._sessions = {}
    runtime._declaration = lambda _key: (pack, declaration, None)
    runtime._session = lambda _key, _declaration, _root: (Session(), card)

    result = runtime.predict_live_snapshot(
        snapshot,
        observed_game_time_s=300.0,
        feature_provider=adapter,
    )

    assert result.status == "available"
    assert result.probability == pytest.approx(0.73)
    assert result.model_version == "fixture-live-v1"
    assert result.pack_version == "fixture-pack-v1"


def test_live_route_exposes_service_probability(tmp_path: Path, monkeypatch) -> None:
    fixture = load_fixture()
    snapshot = deepcopy(fixture["observations"][0]["live"])
    snapshot["observed_at_s"] = time.time()
    snapshot["gameData"]["gameVersion"] = fixture["patch"]
    snapshot["activePlayer"]["summonerName"] = "FixturePlayer01"
    provider = LiveWpFeatureProvider(StaticCatalogProvider(catalog(fixture)))

    class FixtureService(LiveService):
        def __init__(self, *args, **kwargs):
            super().__init__(
                FixtureLcu(),
                FixtureIngame(snapshot),
                args[2],
                inference=RecordingRuntime(),
                feature_provider=kwargs["feature_provider"],
            )

        async def start(self) -> None:
            snapshot["observed_at_s"] = time.time()
            await self.tick()

        async def stop(self) -> None:
            return None

    monkeypatch.setattr(live_module, "LiveService", FixtureService)
    token = "test-token-123456789012345678901234"
    config = SidecarConfig(
        port=23110,
        token=token,
        data_dir=tmp_path / "data",
    )

    with TestClient(
        create_app(
            config,
            credential_store=InMemoryCredentialStore(),
            live_feature_provider=provider,
        )
    ) as client:
        response = client.get(
            "/live/ingame",
            headers={"X-BL-Token": token, "Host": "127.0.0.1:23110"},
        )

    assert response.status_code == 200
    payload = response.json()
    assert payload["inference"]["status"] == "available"
    assert payload["inference"]["probability"] == pytest.approx(0.73)
    assert payload["inference"]["observed_game_time_s"] == pytest.approx(300.0)


async def _versions_only(version: str) -> list[str]:
    return [version]


async def test_official_live_lifecycle_refreshes_patch_on_reconnect_clock_reset_and_end():
    game = deepcopy(load_fixture()["observations"][0]["live"])
    game["gameData"].pop("gameId", None)
    game["gameData"].pop("gameVersion", None)
    snapshots = []
    for clock in [100, 110, None, 120, 5, 8]:
        observation = deepcopy(game) if clock is not None else None
        if observation is not None:
            observation["gameData"]["gameTime"] = clock
        snapshots.append(observation)

    class Lcu:
        version_calls = 0
        phases = iter(["InProgress"] * 5 + ["EndOfGame", "InProgress"])
        async def gameflow_phase(self):
            return next(self.phases)
        async def client_version(self):
            self.version_calls += 1
            return f"16.{self.version_calls}.1"

    class Ingame:
        observations = iter(snapshots)
        async def allgamedata(self):
            return next(self.observations)

    class Provider:
        last_reason = "fixture suppression"
        patches = []
        resets = 0
        async def prepare(self, raw_game, **kwargs):
            self.patches.append(kwargs.get("patch"))
            return None
        def reset_stream(self):
            self.resets += 1

    lcu, provider = Lcu(), Provider()
    service = LiveService(lcu, Ingame(), Hub(), inference=RecordingRuntime(), feature_provider=provider)
    for _ in range(7):
        await service.tick()
        if not service.ingame()["active"]:
            assert service._discovered_patch is None
    assert lcu.version_calls == 4
    assert [patch for patch in provider.patches if patch is not None] == ["16.1.1", "16.1.1", "16.2.1", "16.3.1", "16.4.1"]
    assert service.status()["ingame"]["game_id"] is None


async def test_official_live_patch_retry_is_bounded_and_end_evidence_is_observed(monkeypatch):
    game = deepcopy(load_fixture()["observations"][0]["live"])
    game["gameData"].pop("gameId", None)
    game["gameData"].pop("gameVersion", None)
    game["gameData"]["gameTime"] = 100
    game["events"] = {"Events": [{"EventName": "GameEnd", "EventTime": 200}]}
    receipt = [0.0]
    monkeypatch.setattr(live_module.time, "monotonic", lambda: receipt[0])

    class Lcu:
        calls = 0
        async def gameflow_phase(self):
            return "InProgress"
        async def client_version(self):
            self.calls += 1
            return None

    class Ingame:
        async def allgamedata(self):
            return deepcopy(game)

    lcu = Lcu()
    service = LiveService(lcu, Ingame(), Hub())
    for now in [0, 2, 9, 10, 11, 20, 30, 100]:
        receipt[0] = now
        await service.tick()
        assert service.ingame()["active"] is True  # future GameEnd is not evidence
    assert lcu.calls == 3
    assert service._discovered_patch is None
    game["gameData"]["gameTime"] = 200
    await service.tick()
    assert service.ingame()["active"] is False
    assert service._discovered_patch is None
    await service.tick()
    assert lcu.calls == 3
    # A clock reset with no end event is a new observable lifecycle.
    game["events"] = {"Events": []}
    game["gameData"]["gameTime"] = 5
    await service.tick()
    assert lcu.calls == 4


@pytest.mark.parametrize("clock", [None, "invalid", float("nan"), float("inf"), -1, True])
async def test_malformed_live_clock_does_not_fetch_patch(clock):
    game = deepcopy(load_fixture()["observations"][0]["live"])
    game["gameData"]["gameTime"] = clock

    class Lcu:
        async def gameflow_phase(self):
            return "InProgress"
        async def client_version(self):
            raise AssertionError("malformed observation cannot start patch discovery")

    service = LiveService(Lcu(), FixtureIngame(game), Hub())
    await service.tick()
    await service.tick()
    assert service.ingame()["active"] is False
    assert service._patch_attempts == 0
