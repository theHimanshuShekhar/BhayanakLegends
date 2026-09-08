from __future__ import annotations

from copy import deepcopy
import json
from pathlib import Path
from types import SimpleNamespace

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
    runtime._pack_store = SimpleNamespace(pack_dir=Path("."))
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
            await self.tick()

        async def stop(self) -> None:
            return None

    monkeypatch.setattr(live_module, "LiveService", FixtureService)
    token = "test-token-123456789012345678901234"
    config = SidecarConfig(
        port=23110,
        token=token,
        data_dir=tmp_path / "data",
        pack_dir=Path(__file__).resolve().parents[2] / "pack",
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
