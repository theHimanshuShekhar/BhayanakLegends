import httpx
import pytest

from bhayanak_legends.riot_client import (
    RATE_LIMIT_MIN_INTERVAL_S,
    RateLimiter,
    RiotClient,
    RiotError,
    RiotForbidden,
    RiotNotFound,
    RiotRateLimited,
    RiotRecoverableError,
    USER_AGENT,
)


class FakeClock:
    def __init__(self) -> None:
        self.now = 1000.0

    def __call__(self) -> float:
        return self.now


class Sleeper:
    def __init__(self, clock: FakeClock) -> None:
        self.clock = clock
        self.spans: list[float] = []

    async def __call__(self, seconds: float) -> None:
        self.spans.append(seconds)
        self.clock.now += seconds


def test_rate_limiter_first_acquire_is_immediate():
    limiter = RateLimiter(monotonic=FakeClock())
    assert limiter.acquire() == 0.0


def test_rate_limiter_enforces_min_interval():
    limiter = RateLimiter(monotonic=FakeClock())
    assert limiter.acquire() == 0.0
    second = limiter.acquire()
    assert 0 < second <= RATE_LIMIT_MIN_INTERVAL_S + 1e-9


def test_rate_limiter_120s_window_backpressure():
    clock = FakeClock()
    limiter = RateLimiter(max_per_120s=3, min_interval_s=0.0, monotonic=clock)
    for _ in range(3):
        assert limiter.acquire() == 0.0
        clock.now += 0.01
    fourth = limiter.acquire()
    assert 0 < fourth <= 120.0


def make_client(handler, **kwargs) -> tuple[RiotClient, Sleeper]:
    clock = FakeClock()
    sleeper = Sleeper(clock)
    transport = httpx.MockTransport(handler)
    http = httpx.AsyncClient(
        transport=transport,
        base_url="https://sea.api.riotgames.com",
        headers={"X-Riot-Token": "key", "User-Agent": USER_AGENT},
    )
    client = RiotClient("key", "sea", http_client=http, sleep=sleeper, monotonic=clock, **kwargs)
    return client, sleeper


async def test_match_404_raises_not_found_without_real_http():
    seen_headers = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen_headers.update(request.headers)
        return httpx.Response(404)

    client, _ = make_client(handler)
    with pytest.raises(RiotNotFound):
        await client.match("SG2_1")
    await client.aclose()
    assert seen_headers["user-agent"] == USER_AGENT
    assert seen_headers["x-riot-token"] == "key"


async def test_forbidden_raises():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(403)

    client, _ = make_client(handler)
    with pytest.raises(RiotForbidden):
        await client.match_ids("puuid-1", total=10)
    await client.aclose()


async def test_429_sleeps_retry_then_succeeds():
    calls = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        if calls["n"] == 1:
            return httpx.Response(429, headers={"Retry-After": "7"})
        return httpx.Response(200, json=["SG2_1", "SG2_2"])

    client, sleeper = make_client(handler)
    ids = await client.match_ids("puuid-1", total=2)
    await client.aclose()

    assert ids == ["SG2_1", "SG2_2"]
    assert calls["n"] == 2
    assert 7 in sleeper.spans


async def test_retries_transport_5xx_and_429_with_bounded_budget():
    calls = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        if calls["n"] == 1:
            raise httpx.ConnectError("offline", request=request)
        if calls["n"] == 2:
            return httpx.Response(503)
        if calls["n"] == 3:
            return httpx.Response(429, headers={"Retry-After": "7"})
        return httpx.Response(200, json=["SG2_1", "SG2_2"])

    client, sleeper = make_client(handler)
    ids = await client.match_ids("puuid-1", total=2)
    await client.aclose()

    assert ids == ["SG2_1", "SG2_2"]
    assert calls["n"] == 4
    assert sleeper.spans == [1.0, 2.0, 7.0]



async def test_retry_budget_exhaustion_does_not_sleep_after_final_attempt():
    calls = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        return httpx.Response(503)

    client, sleeper = make_client(handler)
    with pytest.raises(RiotRecoverableError) as caught:
        await client.match("SG2_1")
    await client.aclose()

    assert calls["n"] == 4
    assert sleeper.spans == [1.0, 2.0, 4.0]
    assert caught.value.status_code == 503


async def test_transport_exhaustion_is_recoverable():
    calls = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        raise httpx.ReadTimeout("offline", request=request)

    client, sleeper = make_client(handler)
    with pytest.raises(RiotRecoverableError):
        await client.match("SG2_1")
    await client.aclose()

    assert calls["n"] == 4
    assert sleeper.spans == [1.0, 2.0, 4.0]


async def test_rate_limit_exhaustion_preserves_recoverable_category():
    calls = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        return httpx.Response(429, headers={"Retry-After": "5"})

    client, sleeper = make_client(handler)
    with pytest.raises(RiotRateLimited) as caught:
        await client.match("SG2_1")
    await client.aclose()

    assert calls["n"] == 4
    assert sleeper.spans == [5.0, 5.0, 5.0]
    assert caught.value.retry_after_s == 5.0


@pytest.mark.parametrize(
    ("status", "exception"),
    [
        (400, httpx.HTTPStatusError),
        (401, httpx.HTTPStatusError),
        (403, RiotForbidden),
        (404, RiotNotFound),
        (409, httpx.HTTPStatusError),
    ],
)
async def test_non_retryable_4xx_is_single_attempt(status: int, exception: type[Exception]):
    calls = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        return httpx.Response(status)

    client, sleeper = make_client(handler)
    with pytest.raises(exception):
        await client.match("SG2_1")
    await client.aclose()

    assert calls["n"] == 1
    assert sleeper.spans == []
@pytest.mark.parametrize("status", [201, 204, 206])
async def test_unexpected_success_is_single_attempt(status: int):
    calls = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        return httpx.Response(status)

    client, sleeper = make_client(handler)
    with pytest.raises(RiotError, match="unexpected"):
        await client.match("SG2_1")
    await client.aclose()

    assert calls["n"] == 1
    assert sleeper.spans == []


@pytest.mark.parametrize(
    ("retry_after", "expected_delay"),
    [
        (None, 1.0),
        ("invalid", 1.0),
        ("-1", 1.0),
        ("10", 10.0),
        ("999", 120.0),
    ],
)
async def test_retry_after_is_defensive_and_capped(retry_after: str | None, expected_delay: float):
    calls = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        if calls["n"] == 1:
            headers = {} if retry_after is None else {"Retry-After": retry_after}
            return httpx.Response(429, headers=headers)
        return httpx.Response(200, json={"ok": True})

    client, sleeper = make_client(handler)
    payload = await client.match("SG2_1")
    await client.aclose()

    assert payload == {"ok": True}
    assert calls["n"] == 2
    assert sleeper.spans == [expected_delay]


@pytest.mark.parametrize("status", [500, 501, 550, 599])
async def test_every_5xx_status_is_retried(status: int):
    calls = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        return httpx.Response(status) if calls["n"] == 1 else httpx.Response(200, json={"ok": True})

    client, sleeper = make_client(handler)
    payload = await client.match("SG2_1")
    await client.aclose()

    assert payload == {"ok": True}
    assert calls["n"] == 2
    assert sleeper.spans == [1.0]

async def test_match_ids_paginates_until_short_page():
    pages = {
        0: [f"SG2_{i}" for i in range(100)],
        100: ["SG2_extra"],
    }

    def handler(request: httpx.Request) -> httpx.Response:
        start = int(request.url.params["start"])
        return httpx.Response(200, json=pages.get(start, []))

    client, _ = make_client(handler)
    ids = await client.match_ids("puuid-1", total=500)
    await client.aclose()

    assert len(ids) == 101
    assert ids[-1] == "SG2_extra"


async def test_unknown_region_route_rejected():
    with pytest.raises(ValueError):
        RiotClient("key", "mars")


async def test_account_by_riot_id_quotes_segments():
    captured = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["raw_path"] = request.url.raw_path.decode()
        return httpx.Response(200, json={"puuid": "abc", "gameName": "Sacred Buttholio", "tagLine": "OOF"})

    client, _ = make_client(handler)
    account = await client.account_by_riot_id("Sacred Buttholio#OOF")
    await client.aclose()

    assert account["puuid"] == "abc"
    assert captured["raw_path"] == "/riot/account/v1/accounts/by-riot-id/Sacred%20Buttholio/OOF"
