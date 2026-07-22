"""Fetch the PLACSP ATOM feed and iterate its entries."""

from __future__ import annotations

from collections.abc import Iterator

import httpx
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

from adjudica.config import PLACSP_FEED_URL, TED_DEFAULT_TIMEOUT
from adjudica.placsp.models import PlacspEntry
from adjudica.placsp.parse import iter_entries

_RETRYABLE = (httpx.TransportError, httpx.HTTPStatusError)


@retry(
    retry=retry_if_exception_type(_RETRYABLE),
    wait=wait_exponential(multiplier=1, min=2, max=30),
    stop=stop_after_attempt(4),
    reraise=True,
)
def fetch_feed(client: httpx.Client, url: str = PLACSP_FEED_URL) -> bytes:
    """Download one ATOM feed page (raw bytes). The feed is large (~15 MB)."""
    resp = client.get(url, follow_redirects=True, timeout=TED_DEFAULT_TIMEOUT)
    resp.raise_for_status()
    return resp.content


def iter_feed(
    client: httpx.Client,
    url: str = PLACSP_FEED_URL,
    *,
    max_entries: int | None = None,
) -> Iterator[PlacspEntry]:
    """Fetch the current feed page and yield its entries (capped by max_entries)."""
    entries = iter_entries(fetch_feed(client, url))
    for i, entry in enumerate(entries):
        if max_entries is not None and i >= max_entries:
            return
        yield entry
