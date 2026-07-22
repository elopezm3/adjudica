"""End-to-end extraction eval wiring — extractor + harness, offline."""

import datetime as dt
from types import SimpleNamespace

from adjudica.evals.extraction import Grade
from adjudica.evals.run_extraction import evaluate_documents
from adjudica.extract.schema import ExtractedFields
from adjudica.ingest.models import NoticeRecord

_PDF = b"%PDF-1.4 body"


class ScriptedClient:
    """Returns a queued ExtractedFields for each parse() call, in order."""

    def __init__(self, outputs):
        self._outputs = list(outputs)
        self.messages = SimpleNamespace(parse=self._parse)

    def _parse(self, **kwargs):
        return SimpleNamespace(parsed_output=self._outputs.pop(0), stop_reason="end_turn")


def _tender(budget, cpv, deadline):
    return NoticeRecord(
        publication_number="T",
        notice_type="cn-standard",
        kind="tender",
        estimated_value=budget,
        cpv_primary=cpv,
        deadline=deadline,
    )


def test_scores_correct_and_wrong_extractions():
    truth1 = _tender(100000.0, "72000000", dt.date(2024, 10, 1))
    truth2 = _tender(50000.0, "45000000", dt.date(2024, 9, 15))
    client = ScriptedClient(
        [
            ExtractedFields(budget=100000.0, cpv_primary="72000000", deadline=dt.date(2024, 10, 1)),
            ExtractedFields(budget=50000.0, cpv_primary="99999999", deadline=dt.date(2024, 9, 15)),
        ]
    )
    card = evaluate_documents([(_PDF, truth1), (_PDF, truth2)], client=client)
    # cpv: one right, one wrong; budget + deadline: both right.
    assert card.per_field["cpv_primary"] == {
        "match": 1,
        "mismatch": 1,
        "no_ground_truth": 0,
        "accuracy": 0.5,
    }
    assert card.per_field["budget"]["accuracy"] == 1.0


def test_unreadable_document_counts_as_all_missed_not_dropped():
    truth = _tender(100000.0, "72000000", dt.date(2024, 10, 1))
    # A .docx (non-PDF) can't be extracted -> empty fields -> every gradable field misses.
    card = evaluate_documents([(b"PK\x03\x04 docx", truth)], client=ScriptedClient([]))
    grades = {f: v for f, v in card.per_field.items()}
    assert grades["budget"]["mismatch"] == 1
    assert grades["cpv_primary"]["mismatch"] == 1
    assert grades["deadline"]["mismatch"] == 1
    assert card.overall_accuracy == 0.0  # nothing correct, all gradable -> 0%
    # And the grade for each is MISMATCH, not skipped.
    assert Grade.MISMATCH  # sanity: enum importable
