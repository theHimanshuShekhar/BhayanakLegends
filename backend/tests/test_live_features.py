"""Behavioral contract tests for exact Live WP feature parity."""

from __future__ import annotations

from copy import deepcopy
import json
from pathlib import Path

import pytest

from bhayanak_legends.live_features import (
    DataDragonCatalog,
    FEATURE_ORDER,
    LIVE_FEATURE_REGISTRY,
    LIVE_WP_CONTRACT_VERSION,
    MAX_CAPTURE_AGE_S,
    adapt_live_client_state,
    adapt_timeline_state,
)


FIXTURE = Path(__file__).parent / "fixtures" / "live_wp_v2_parity.json"


def load_fixture() -> dict:
    return json.loads(FIXTURE.read_text(encoding="utf-8"))


def catalog(fixture: dict) -> DataDragonCatalog:
    return DataDragonCatalog(
        fixture["data_dragon_version"],
        {int(item_id): float(cost) for item_id, cost in fixture["data_dragon_items"].items()},
    )


def assert_values(vector, expected: list[float]) -> None:
    assert vector is not None
    assert vector.contract_version == LIVE_WP_CONTRACT_VERSION
    assert vector.values == pytest.approx(expected)
    assert len(vector.values) == len(FEATURE_ORDER)


def test_registry_order_and_metadata_are_mechanical() -> None:
    fixture = load_fixture()
    assert LIVE_FEATURE_REGISTRY.version == fixture["contract_version"]
    assert FEATURE_ORDER == tuple(fixture["feature_order"])
    assert LIVE_FEATURE_REGISTRY.live_poll_interval_s == 2.0
    assert LIVE_FEATURE_REGISTRY.max_capture_age_s == MAX_CAPTURE_AGE_S == 5.0
    assert LIVE_FEATURE_REGISTRY.timeline_frame_interval_s == 60.0
    assert "future events are ignored" in LIVE_FEATURE_REGISTRY.missing_data_policy.lower()
    assert "major.minor" in LIVE_FEATURE_REGISTRY.patch_semantics
    assert not any("gold" in name.lower() or "xp" in name.lower() for name in FEATURE_ORDER)


def test_training_and_live_adapters_match_every_timestamp_and_side() -> None:
    fixture = load_fixture()
    items = catalog(fixture)
    for observation in fixture["observations"]:
        time_s = float(observation["time_s"])
        for side in (100, 200):
            expected = observation["expected"][str(side)]
            training = adapt_timeline_state(
                fixture["match"], fixture["timeline"], time_s, side, items
            )
            assert_values(training, expected)

            live = deepcopy(observation["live"])
            live["activePlayer"]["summonerName"] = "FixturePlayer01" if side == 100 else "FixturePlayer06"
            online = adapt_live_client_state(
                live, fixture["patch"], items, observed_at_s=time_s, now_s=time_s
            )
            assert_values(online, expected)


def test_side_mirroring_is_signed_and_does_not_change_elapsed_time() -> None:
    fixture = load_fixture()
    items = catalog(fixture)
    observation = fixture["observations"][1]
    blue = adapt_timeline_state(fixture["match"], fixture["timeline"], 600, 100, items)
    red = adapt_timeline_state(fixture["match"], fixture["timeline"], 600, 200, items)
    assert blue is not None and red is not None
    assert blue.values[0] == red.values[0] == 600
    assert red.values[1:] == pytest.approx(tuple(-value for value in blue.values[1:]))
    assert blue.values == pytest.approx(observation["expected"]["100"])


def test_future_objectives_and_kills_never_leak_into_earlier_state() -> None:
    fixture = load_fixture()
    vector = adapt_timeline_state(
        fixture["match"], fixture["timeline"], 600, 100, catalog(fixture)
    )
    assert_values(vector, fixture["observations"][1]["expected"]["100"])
    # Herald/Baron and the later kill occur at 700s+ and are absent at 600s.
    assert vector is not None
    assert vector.values[FEATURE_ORDER.index("team_heralds_diff")] == 0
    assert vector.values[FEATURE_ORDER.index("team_barons_diff")] == 0
    assert vector.values[FEATURE_ORDER.index("team_kills_diff")] == 0


def test_missing_stale_unsupported_and_ambiguous_inputs_suppress() -> None:
    fixture = load_fixture()
    items = catalog(fixture)
    live = deepcopy(fixture["observations"][0]["live"])
    assert adapt_live_client_state(live, fixture["patch"], items, observed_at_s=10, now_s=10 + MAX_CAPTURE_AGE_S) is not None
    assert adapt_live_client_state(live, fixture["patch"], items, observed_at_s=10, now_s=10 + MAX_CAPTURE_AGE_S + 0.001) is None

    missing = deepcopy(live)
    del missing["allPlayers"][0]["scores"]["creepScore"]
    assert adapt_live_client_state(missing, fixture["patch"], items) is None

    unsupported_item = deepcopy(live)
    unsupported_item["allPlayers"][0]["items"][0]["itemID"] = 999999
    assert adapt_live_client_state(unsupported_item, fixture["patch"], items) is None

    unsupported_patch = adapt_live_client_state(live, "16.18", items)
    assert unsupported_patch is None

    ambiguous_team = deepcopy(fixture["match"])
    ambiguous_team["info"]["participants"][0]["teamId"] = 300
    assert adapt_timeline_state(ambiguous_team, fixture["timeline"], 300, 100, items) is None

    missing_frame_field = deepcopy(fixture["timeline"])
    del missing_frame_field["info"]["frames"][1]["participantFrames"]["1"]["level"]
    assert adapt_timeline_state(fixture["match"], missing_frame_field, 300, 100, items) is None


def test_event_actor_and_local_side_must_be_unambiguous() -> None:
    fixture = load_fixture()
    items = catalog(fixture)
    live = deepcopy(fixture["observations"][0]["live"])
    live["events"]["Events"][0]["KillerName"] = "not-a-team-or-player"
    assert adapt_live_client_state(live, fixture["patch"], items) is None

    no_local = deepcopy(fixture["observations"][0]["live"])
    no_local["activePlayer"]["summonerName"] = "missing-player"
    assert adapt_live_client_state(no_local, fixture["patch"], items) is None

    # Champ-select data, including enemy identities, is not an input to this seam.
    unrelated = deepcopy(fixture["observations"][0]["live"])
    unrelated["champSelect"] = {"enemy": [{"name": "not-used"}]}
    baseline = adapt_live_client_state(fixture["observations"][0]["live"], fixture["patch"], items)
    ignored = adapt_live_client_state(unrelated, fixture["patch"], items)
    assert baseline is not None and ignored is not None
    assert ignored.values == baseline.values
