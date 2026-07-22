"""Extractor tests with a fake Anthropic client — fully offline."""

import base64
import datetime as dt
from types import SimpleNamespace

import pytest

from adjudica.extract.extractor import (
    ExtractionError,
    UnsupportedDocumentError,
    extract_from_pdf,
)
from adjudica.extract.schema import ExtractedFields

_TINY_PDF = b"%PDF-1.4 fake body"


class FakeMessages:
    """Records the parse() call and returns a preset response."""

    def __init__(self, parsed=None, stop_reason="end_turn"):
        self._parsed = parsed
        self._stop_reason = stop_reason
        self.last_kwargs = None

    def parse(self, **kwargs):
        self.last_kwargs = kwargs
        return SimpleNamespace(parsed_output=self._parsed, stop_reason=self._stop_reason)


class FakeClient:
    def __init__(self, parsed=None, stop_reason="end_turn"):
        self.messages = FakeMessages(parsed, stop_reason)


def test_returns_parsed_fields():
    want = ExtractedFields(budget=331252.82, cpv_primary="90911200", deadline=dt.date(2025, 2, 10))
    client = FakeClient(parsed=want)
    got = extract_from_pdf(_TINY_PDF, client=client)
    assert got == want


def test_sends_pdf_as_base64_document_before_text():
    client = FakeClient(parsed=ExtractedFields())
    extract_from_pdf(_TINY_PDF, client=client)
    content = client.messages.last_kwargs["messages"][0]["content"]

    doc, text = content[0], content[1]
    assert doc["type"] == "document"
    assert doc["source"]["media_type"] == "application/pdf"
    assert base64.standard_b64decode(doc["source"]["data"]) == _TINY_PDF
    assert text["type"] == "text"  # document precedes the instruction text
    assert client.messages.last_kwargs["output_format"] is ExtractedFields


def test_non_pdf_raises_unsupported():
    client = FakeClient(parsed=ExtractedFields())
    with pytest.raises(UnsupportedDocumentError):
        extract_from_pdf(b"PK\x03\x04 this is a docx", client=client)


def test_refusal_raises_extraction_error():
    client = FakeClient(parsed=None, stop_reason="refusal")
    with pytest.raises(ExtractionError):
        extract_from_pdf(_TINY_PDF, client=client)


def test_missing_parsed_output_raises():
    client = FakeClient(parsed=None, stop_reason="end_turn")
    with pytest.raises(ExtractionError):
        extract_from_pdf(_TINY_PDF, client=client)
