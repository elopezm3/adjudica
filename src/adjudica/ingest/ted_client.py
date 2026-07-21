"""HTTP client for the TED v3 search API.

Verified live (2026-07): POST /v3/notices/search, HTTP 200, no API key required.
Envelope: {"notices": [...], "totalNoticeCount": N, "iterationNextToken": <cursor|null>}.
Pagination is cursor-based via iterationNextToken.

Rate limiting is real (observed a 429 during backfill). We handle it two ways:
- proactively throttle to a minimum interval between requests, and
- retry on 429, honoring a Retry-After header when present.
Genuine 4xx (bad query/fields) stay fatal — retrying them is pointless.
"""

from __future__ import annotations

import time
from collections.abc import Iterator
from typing import Any

import httpx
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

from adjudica.config import (
    TED_DEFAULT_TIMEOUT,
    TED_FIELDS,
    TED_MAX_PAGE_SIZE,
    TED_MIN_REQUEST_INTERVAL_S,
    TED_SEARCH_URL,
)

_RETRYABLE = (httpx.TransportError, httpx.HTTPStatusError)


class TedError(RuntimeError):
    """A TED API call failed in a way we won't retry (e.g. a 400 bad query)."""


def _wait_strategy(retry_state) -> float:
    """Honor a Retry-After header on 429s; otherwise exponential backoff."""
    exc = retry_state.outcome.exception()
    if isinstance(exc, httpx.HTTPStatusError):
        retry_after = exc.response.headers.get("retry-after")
        if retry_after:
            try:
                return float(retry_after) + 0.5
            except ValueError:
                pass
    return wait_exponential(multiplier=1, min=2, max=60)(retry_state)


class TedClient:
    """Thin wrapper over the TED search API with throttling, retry, and pagination."""

    def __init__(
        self,
        client: httpx.Client | None = None,
        *,
        fields: tuple[str, ...] = TED_FIELDS,
        page_size: int = TED_MAX_PAGE_SIZE,
        min_interval_s: float = TED_MIN_REQUEST_INTERVAL_S,
    ) -> None:
        self._client = client or httpx.Client(timeout=TED_DEFAULT_TIMEOUT)
        self._owns_client = client is None
        self._fields = list(fields)
        self._page_size = page_size
        self._min_interval_s = min_interval_s
        self._last_request_at = 0.0

    def __enter__(self) -> TedClient:
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()

    def close(self) -> None:
        if self._owns_client:
            self._client.close()

    def _throttle(self) -> None:
        if self._min_interval_s <= 0:
            return
        elapsed = time.monotonic() - self._last_request_at
        if elapsed < self._min_interval_s:
            time.sleep(self._min_interval_s - elapsed)

    @retry(
        retry=retry_if_exception_type(_RETRYABLE),
        wait=_wait_strategy,
        stop=stop_after_attempt(6),
        reraise=True,
    )
    def _search_page(self, query: str, token: str | None) -> dict[str, Any]:
        body: dict[str, Any] = {
            "query": query,
            "limit": self._page_size,
            "fields": self._fields,
            "paginationMode": "ITERATION",
        }
        if token:
            # Verified live: the request cursor param is symmetric with the response
            # envelope field, both named iterationNextToken (not iterationToken).
            body["iterationNextToken"] = token

        self._throttle()
        resp = self._client.post(TED_SEARCH_URL, json=body)
        self._last_request_at = time.monotonic()

        # 429 (rate limited) and 5xx are transient -> raise HTTPStatusError -> retried.
        if resp.status_code == 429 or resp.status_code >= 500:
            resp.raise_for_status()
        # Other 4xx are our fault (bad query/fields) -> fatal.
        if resp.status_code >= 400:
            raise TedError(f"TED {resp.status_code}: {resp.text[:500]}")
        return resp.json()

    def iter_notices(
        self, query: str, *, max_notices: int | None = None
    ) -> Iterator[dict[str, Any]]:
        """Yield raw notice dicts for a query, following the cursor to completion.

        `max_notices` caps how many are yielded (useful for sampling); None = all.
        """
        token: str | None = None
        yielded = 0
        while True:
            page = self._search_page(query, token)
            for notice in page.get("notices", []):
                yield notice
                yielded += 1
                if max_notices is not None and yielded >= max_notices:
                    return
            token = page.get("iterationNextToken")
            if not token:
                return
