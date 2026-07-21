"""TedClient tests using httpx MockTransport — no real network, safe in CI.

These pin the pagination contract verified live on 2026-07:
- request carries paginationMode=ITERATION and (after page 1) iterationNextToken
- the client follows iterationNextToken until it is null
"""

import httpx
import pytest

from adjudica.ingest.ted_client import TedClient, TedError


def _page(notices, next_token):
    return {"notices": notices, "totalNoticeCount": 99, "iterationNextToken": next_token}


def test_iter_notices_follows_cursor_to_completion():
    seen_bodies = []

    def handler(request: httpx.Request) -> httpx.Response:
        body = request.read().decode()
        seen_bodies.append(body)
        import json

        token = json.loads(body).get("iterationNextToken")
        if token is None:
            return httpx.Response(200, json=_page([{"publication-number": "1"}], "TOK"))
        return httpx.Response(200, json=_page([{"publication-number": "2"}], None))

    import json

    client = httpx.Client(transport=httpx.MockTransport(handler))
    with TedClient(client, min_interval_s=0) as ted:
        got = list(ted.iter_notices("q"))

    first, second = json.loads(seen_bodies[0]), json.loads(seen_bodies[1])
    assert [n["publication-number"] for n in got] == ["1", "2"]
    assert first["paginationMode"] == "ITERATION"
    assert "iterationNextToken" not in first  # no cursor on first call
    assert second["iterationNextToken"] == "TOK"  # cursor sent on second


def test_max_notices_caps_and_stops_early():
    def handler(request: httpx.Request) -> httpx.Response:
        # Always offers a next token; the cap must stop us anyway.
        return httpx.Response(200, json=_page([{"publication-number": "x"}], "MORE"))

    client = httpx.Client(transport=httpx.MockTransport(handler))
    with TedClient(client, min_interval_s=0) as ted:
        got = list(ted.iter_notices("q", max_notices=3))
    assert len(got) == 3


def test_4xx_raises_tederror_without_retry():
    calls = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        return httpx.Response(400, text="bad query")

    client = httpx.Client(transport=httpx.MockTransport(handler))
    with TedClient(client, min_interval_s=0) as ted, pytest.raises(TedError):
        list(ted.iter_notices("q"))
    assert calls["n"] == 1  # 4xx is not retried


def test_429_is_retried_then_succeeds():
    # 429 is rate limiting, not a bad request: back off (honoring Retry-After) and retry.
    calls = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        if calls["n"] <= 2:
            return httpx.Response(429, headers={"retry-after": "0"}, text="slow down")
        return httpx.Response(200, json=_page([{"publication-number": "ok"}], None))

    client = httpx.Client(transport=httpx.MockTransport(handler))
    with TedClient(client, min_interval_s=0) as ted:
        got = list(ted.iter_notices("q"))
    assert [n["publication-number"] for n in got] == ["ok"]
    assert calls["n"] == 3  # two 429s, then success
