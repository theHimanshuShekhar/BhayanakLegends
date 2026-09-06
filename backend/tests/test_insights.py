from __future__ import annotations

from bhayanak_legends.insights import aggregate_insights


def match(
    match_id: str,
    *,
    played_at: str = "2026-01-01T00:00:00Z",
    role: str | None = "MIDDLE",
    champion: str | None = "Ahri",
    win: bool = True,
) -> dict:
    return {
        "match_id": match_id,
        "played_at": played_at,
        "role": role,
        "champion": champion,
        "win": win,
    }


def test_profiles_group_unknown_roles_and_same_champion_across_roles() -> None:
    result = aggregate_insights(
        [
            match("a", role="MIDDLE", champion="Ahri", win=True),
            match("b", role="MIDDLE", champion="Ahri", win=False),
            match("c", role="UTILITY", champion="Ahri", win=True),
            match("d", role=None, champion="Ahri", win=False),
            match("e", role="not-a-role", champion=None, win=True),
        ]
    )

    assert result["state"] == "available"
    assert result["sample_size"] == 5
    assert {row["role"]: row for row in result["roles"]} == {
        "MIDDLE": {
            "role": "MIDDLE",
            "games": 2,
            "wins": 1,
            "win_rate": 0.5,
            "sample_status": "insufficient",
        },
        "UTILITY": {
            "role": "UTILITY",
            "games": 1,
            "wins": 1,
            "win_rate": 1.0,
            "sample_status": "insufficient",
        },
        "UNKNOWN": {
            "role": "UNKNOWN",
            "games": 2,
            "wins": 1,
            "win_rate": 0.5,
            "sample_status": "insufficient",
        },
    }
    champions = {row["champion"]: row for row in result["champions"]}
    assert champions["Ahri"]["games"] == 4
    assert champions["Ahri"]["wins"] == 2
    assert champions["Ahri"]["roles"] == ["MIDDLE", "UTILITY", "UNKNOWN"]
    assert champions["UNKNOWN"]["games"] == 1


def test_filters_apply_before_profiles_and_review_windows() -> None:
    rows = [
        match(f"ahri-{index:03d}", played_at=f"2026-01-01T00:{index:02d}:00Z", champion="Ahri", win=index % 2 == 0)
        for index in range(60)
    ] + [
        match(f"jinx-{index:03d}", played_at=f"2026-01-02T00:{index:02d}:00Z", champion="Jinx")
        for index in range(60)
    ]

    result = aggregate_insights(rows, role="middle", champion="Ahri")

    assert result["filters"] == {"role": "MIDDLE", "champion": "Ahri"}
    assert result["sample_size"] == 60
    assert result["champions"] == [
        {
            "champion": "Ahri",
            "games": 60,
            "wins": 30,
            "win_rate": 0.5,
            "roles": ["MIDDLE"],
            "sample_status": "review",
        }
    ]
    assert result["windows"]["latest"]["games"] == 50
    assert result["windows"]["latest"]["wins"] == 25
    assert result["windows"]["latest"]["completeness"] == "full"
    assert result["windows"]["preceding"]["games"] == 10
    assert result["windows"]["preceding"]["completeness"] == "partial"


def test_windows_are_honest_for_short_and_exact_histories() -> None:
    def rows(count: int) -> list[dict]:
        return [
            match(
                f"m-{index:03d}",
                played_at=f"2026-01-01T00:{index:02d}:00Z",
                win=index % 2 == 0,
            )
            for index in range(count)
        ]

    fewer_than_50 = aggregate_insights(rows(12))
    assert fewer_than_50["windows"] == {
        "latest": {
            "name": "latest",
            "games": 12,
            "wins": 6,
            "win_rate": 0.5,
            "sample_status": "review",
            "completeness": "partial",
        },
        "preceding": {
            "name": "preceding",
            "games": 0,
            "wins": 0,
            "win_rate": 0.0,
            "sample_status": "insufficient",
            "completeness": "unavailable",
        },
    }

    exactly_100 = aggregate_insights(rows(100))
    assert exactly_100["windows"]["latest"]["games"] == 50
    assert exactly_100["windows"]["preceding"]["games"] == 50
    assert exactly_100["windows"]["latest"]["completeness"] == "full"
    assert exactly_100["windows"]["preceding"]["completeness"] == "full"

    more_than_100 = aggregate_insights(rows(120))
    assert more_than_100["sample_size"] == 120
    assert more_than_100["windows"]["latest"]["games"] == 50
    assert more_than_100["windows"]["preceding"]["games"] == 50
    assert more_than_100["windows"]["latest"]["completeness"] == "full"
    assert more_than_100["windows"]["preceding"]["completeness"] == "full"


def test_tied_timestamps_use_match_id_as_the_deterministic_tie_breaker() -> None:
    result = aggregate_insights(
        [
            match("z", played_at="2026-01-01T00:00:00Z", win=False),
            match("a", played_at="2026-01-01T00:00:00Z", win=True),
            match("m", played_at="2026-01-02T00:00:00Z", win=True),
        ]
    )

    # The latest row is the final canonical row (m), while the tie is ordered a,z.
    assert result["windows"]["latest"]["wins"] == 2
    assert result["windows"]["latest"]["games"] == 3


def test_empty_or_nonmatching_filters_are_explicit() -> None:
    assert aggregate_insights([])["state"] == "empty"
    result = aggregate_insights([match("one")], role="TOP")
    assert result["state"] == "empty"
    assert result["sample_size"] == 0
    assert result["roles"] == []
    assert result["champions"] == []
    assert result["windows"]["latest"]["completeness"] == "unavailable"
