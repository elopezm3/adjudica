"""PLACSP download + end-to-end pipeline tests — offline via mock transports."""

import datetime as dt
from pathlib import Path
from types import SimpleNamespace

import httpx
import pytest

from adjudica.evals.run_placsp import evaluate_placsp
from adjudica.extract.schema import ExtractedFields
from adjudica.placsp.documents import DocumentDownloadError, download_document

FIXTURE = Path(__file__).parent / "fixtures" / "placsp_sample.atom"
_PDF = b"%PDF-1.4 pliego body"


def test_download_document_returns_bytes():
    def handler(request):
        return httpx.Response(200, content=_PDF)

    client = httpx.Client(transport=httpx.MockTransport(handler))
    assert download_document("https://x/doc", client=client) == _PDF


def test_download_document_raises_on_404():
    client = httpx.Client(transport=httpx.MockTransport(lambda r: httpx.Response(404)))
    with pytest.raises(DocumentDownloadError):
        download_document("https://x/doc", client=client)


class ScriptedAnthropic:
    def __init__(self, outputs):
        self._outputs = list(outputs)
        self.messages = SimpleNamespace(parse=self._parse)

    def _parse(self, **kwargs):
        return SimpleNamespace(parsed_output=self._outputs.pop(0), stop_reason="end_turn")


def test_end_to_end_feed_to_scorecard():
    # HTTP: first call returns the ATOM feed, later calls return a PDF for each document.
    calls = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        if calls["n"] == 1:
            return httpx.Response(200, content=FIXTURE.read_bytes())
        return httpx.Response(200, content=_PDF)

    http_client = httpx.Client(transport=httpx.MockTransport(handler))

    # Perfect extraction for the first gradable entry (budget/cpv/deadline all correct).
    anthropic_client = ScriptedAnthropic(
        [
            ExtractedFields(
                budget=106971.94, cpv_primary="45212200", deadline=dt.date(2026, 8, 10)
            ),
            ExtractedFields(),  # spare in case the 2nd entry is also gradable
        ]
    )

    card = evaluate_placsp(http_client=http_client, anthropic_client=anthropic_client, max_docs=1)
    # One tender graded, all three fields correct -> 100%.
    assert card.per_field["cpv_primary"]["match"] == 1
    assert card.overall_accuracy == 1.0
