"""Download pliego documents from PLACSP GetDocumentByIdServlet links."""

from __future__ import annotations

import httpx
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

from adjudica.config import TED_DEFAULT_TIMEOUT

_RETRYABLE = (httpx.TransportError, httpx.HTTPStatusError)


class DocumentDownloadError(RuntimeError):
    """A document could not be downloaded (non-200 after retries)."""


@retry(
    retry=retry_if_exception_type(_RETRYABLE),
    wait=wait_exponential(multiplier=1, min=2, max=30),
    stop=stop_after_attempt(4),
    reraise=True,
)
def download_document(uri: str, *, client: httpx.Client) -> bytes:
    """Fetch a document's bytes. Content-Type is unreliable here, so callers sniff the
    real type from magic bytes (the extractor does this) rather than trusting headers."""
    resp = client.get(uri, follow_redirects=True)
    if resp.status_code >= 500:
        resp.raise_for_status()  # transient -> retried
    if resp.status_code != 200:
        raise DocumentDownloadError(f"{resp.status_code} for {uri[:80]}")
    return resp.content


def new_client() -> httpx.Client:
    """An httpx client with a browser-ish UA — PLACSP's document servlet expects one."""
    return httpx.Client(
        timeout=TED_DEFAULT_TIMEOUT,
        headers={"User-Agent": "Mozilla/5.0 (compatible; adjudica-research/0.1)"},
    )
