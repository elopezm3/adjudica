"""Wire the extractor to the eval harness: extract each document, grade, score.

This is the Phase-1 end-to-end. Given (document bytes, ground-truth NoticeRecord) pairs,
it extracts fields from each document and scores them against the XML truth. A document
that can't be read (non-PDF, refusal, API error) is graded as an empty extraction — a
miss on every field — never silently dropped, so the accuracy number stays honest.
"""

from __future__ import annotations

from collections.abc import Iterable

from adjudica.evals.extraction import Scorecard, score
from adjudica.extract.extractor import ExtractionError, UnsupportedDocumentError, extract_from_pdf
from adjudica.extract.schema import ExtractedFields
from adjudica.ingest.models import NoticeRecord


def evaluate_documents(
    items: Iterable[tuple[bytes, NoticeRecord]],
    *,
    client,
) -> Scorecard:
    """Extract + grade each (pdf_bytes, tender) pair; return the aggregate Scorecard."""
    pairs: list[tuple[ExtractedFields, NoticeRecord]] = []
    for pdf_bytes, truth in items:
        try:
            extracted = extract_from_pdf(pdf_bytes, client=client)
        except (ExtractionError, UnsupportedDocumentError):
            extracted = ExtractedFields()  # unreadable -> empty -> counts as all-missed
        pairs.append((extracted, truth))
    return score(pairs)
