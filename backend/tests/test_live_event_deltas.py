from __future__ import annotations

import asyncio
from copy import deepcopy
import json
from pathlib import Path

import pytest

from bhayanak_legends.live import LiveEvent, LiveService, _LiveEventDeltaTracker
from bhayanak_legends.live_features import LiveFeatureVector
from bhayanak_legends.models import LiveInference
from bhayanak_legends.sse import Hub


def vector(clock_s: float) -> LiveFeatureVector:
    return LiveFeatureVector(
        contract_version="live-wp-v2",
        side=100,
        observed_at_s=clock_s,
        patch="16.17.791.1234",
        data_dragon_version="16.17.1",
        values=(clock_s, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0),
    )


def inference(clock_s: float, probability: float | None, *, status: str = "available") -> LiveInference:
    return LiveInference(
        status=status,
        probability=probability,
        observed_game_time_s=clock_s,
        model_version="fixture-live-v1",
        pack_version="fixture-pack-v1",
    )


def test_supported_event_delta_uses_two_exact_predictions_and_preserves_source_order() -> None:
    tracker = _LiveEventDeltaTracker()
    events = [
        LiveEvent(name="ChampionKill", t_s=15.0, actor="FixturePlayer25", victim="FixturePlayer27"),
        LiveEvent(name="DragonKill", t_s=20.0, actor="ORDER"),
    ]

    assert tracker.process(events, clock_s=10.0, inference=inference(10.0, 0.4), vector=vector(10.0)) == []
    deltas = tracker.process(events, clock_s=30.0, inference=inference(30.0, 0.55), vector=vector(30.0))

    assert len(deltas) == 1
    delta = deltas[0]
    assert delta.event_id == "0:DragonKill:20.0"
    assert delta.source_order == 0
    assert delta.pre_observed_game_time_s == 10.0
    assert delta.post_observed_game_time_s == 30.0
    assert delta.model_version == "fixture-live-v1"
    assert delta.pack_version == "fixture-pack-v1"
    assert delta.delta_probability == pytest.approx(0.15)


def test_zero_delta_is_available_and_distinct_from_suppressed_delta() -> None:
    tracker = _LiveEventDeltaTracker()
    event = LiveEvent(name="TurretKilled", t_s=20.0, actor="CHAOS")

    tracker.process([], clock_s=10.0, inference=inference(10.0, 0.5), vector=vector(10.0))
    deltas = tracker.process([event], clock_s=30.0, inference=inference(30.0, 0.5), vector=vector(30.0))

    assert deltas[0].suppression_status == "available"
    assert deltas[0].delta_probability == 0.0
    assert deltas[0].reason is None


def test_historical_duplicate_delayed_and_out_of_order_events_suppress_deterministically() -> None:
    tracker = _LiveEventDeltaTracker()
    historical = LiveEvent(name="DragonKill", t_s=20.0, actor="ORDER")
    assert tracker.process([historical], clock_s=30.0, inference=inference(30.0, 0.6), vector=vector(30.0))[0].delta_probability is None

    # Replaying the same cumulative row does not create a second annotation.
    replay = tracker.process([historical], clock_s=40.0, inference=inference(40.0, 0.7), vector=vector(40.0))
    assert len(replay) == 1

    # A newly arrived row behind the previously observed event order is never
    # reordered into a guessed pair.
    delayed = LiveEvent(name="TurretKilled", t_s=15.0, actor="CHAOS")
    deltas = tracker.process([historical, delayed], clock_s=50.0, inference=inference(50.0, 0.8), vector=vector(50.0))
    assert len(deltas) == 2
    delayed_delta = deltas[-1]
    assert delayed_delta.event_id == "1:TurretKilled:15.0"
    assert delayed_delta.delta_probability is None
    assert delayed_delta.suppression_status == "suppressed"
    assert delayed_delta.reason == "event source ordering changed"


def test_unsupported_events_stay_unannotated_and_missing_vectors_are_unavailable() -> None:
    unsupported_tracker = _LiveEventDeltaTracker()
    unsupported = LiveEvent(name="ChampionKill", t_s=20.0, actor="FixturePlayer25", victim="FixturePlayer27")
    unsupported_tracker.process([], clock_s=10.0, inference=inference(10.0, 0.4), vector=vector(10.0))
    assert unsupported_tracker.process(
        [unsupported], clock_s=30.0, inference=inference(30.0, 0.6), vector=vector(30.0)
    ) == []

    missing_tracker = _LiveEventDeltaTracker()
    supported = LiveEvent(name="BaronKill", t_s=20.0, actor="ORDER")
    missing_tracker.process([], clock_s=10.0, inference=inference(10.0, 0.4), vector=None)
    deltas = missing_tracker.process([supported], clock_s=30.0, inference=inference(30.0, 0.6), vector=vector(30.0))
    assert deltas[0].delta_probability is None
    assert deltas[0].suppression_status == "suppressed"
    assert deltas[0].reason == "exact pre/post live vectors unavailable"


def test_multiple_events_crossed_between_observations_are_not_paired() -> None:
    tracker = _LiveEventDeltaTracker()
    events = [
        LiveEvent(name="DragonKill", t_s=20.0, actor="ORDER"),
        LiveEvent(name="TurretKilled", t_s=25.0, actor="CHAOS"),
    ]
    tracker.process([], clock_s=10.0, inference=inference(10.0, 0.4), vector=vector(10.0))
    deltas = tracker.process(events, clock_s=30.0, inference=inference(30.0, 0.6), vector=vector(30.0))

    assert [delta.source_order for delta in deltas] == [0, 1]
    assert all(delta.delta_probability is None for delta in deltas)
    assert all(delta.reason == "multiple supported events crossed between observations" for delta in deltas)


class SequenceLcu:
    async def gameflow_phase(self) -> str:
        return "InProgress"

    async def champ_select_session(self):
        return None


class SequenceIngame:
    def __init__(self, payloads: list[dict]) -> None:
        self.payloads = payloads

    async def allgamedata(self) -> dict:
        return self.payloads.pop(0)


class FixtureRuntime:
    def predict_live_snapshot(self, snapshot, *, observed_game_time_s, feature_provider):
        current = feature_provider(snapshot)
        if current is None:
            return inference(observed_game_time_s, None, status="suppressed")
        probability = 0.4 if observed_game_time_s < 250 else 0.55
        return inference(observed_game_time_s, probability)


async def next_live_state(queue: asyncio.Queue) -> dict:
    while True:
        frame = json.loads(await queue.get())
        if frame["type"] == "live.state":
            return frame["data"]


def fixture_payload(clock_s: float) -> dict:
    fixture_path = Path(__file__).parent / "fixtures" / "live_wp_v2_parity.json"
    fixture = json.loads(fixture_path.read_text(encoding="utf-8"))
    payload = deepcopy(fixture["observations"][0]["live"])
    payload["gameData"]["gameTime"] = clock_s
    payload["gameData"]["gameVersion"] = fixture["patch"]
    payload["events"]["Events"] = [{"EventName": "DragonKill", "EventTime": 250.0, "KillerName": "ORDER"}]
    return payload


@pytest.mark.asyncio
async def test_live_state_sse_transitions_from_unavailable_to_exact_event_delta() -> None:
    def exact_vector(snapshot):
        clock_s = float(snapshot["gameData"]["gameTime"])
        return vector(clock_s)

    hub = Hub()
    queue = hub.subscribe()
    service = LiveService(
        SequenceLcu(),
        SequenceIngame([fixture_payload(200.0), fixture_payload(300.0)]),
        hub,
        inference=FixtureRuntime(),
        feature_provider=exact_vector,
    )

    await service.tick()
    before = await next_live_state(queue)
    assert before["event_deltas"] == []

    await service.tick()
    after = await next_live_state(queue)
    assert len(after["event_deltas"]) == 1
    delta = after["event_deltas"][0]
    assert delta["event_id"] == "0:DragonKill:250.0"
    assert delta["pre_observed_game_time_s"] == 200.0
    assert delta["post_observed_game_time_s"] == 300.0
    assert delta["suppression_status"] == "available"
    assert delta["delta_probability"] == pytest.approx(0.15)
