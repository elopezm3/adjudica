"""Extraction eval harness tests — grading logic, fully offline."""

import datetime as dt

from adjudica.evals.extraction import Grade, grade_notice, score
from adjudica.extract.schema import ExtractedFields
from adjudica.ingest.models import NoticeRecord


def _tender(budget=None, cpv="72000000", deadline=dt.date(2024, 10, 1)) -> NoticeRecord:
    return NoticeRecord(
        publication_number="T",
        notice_type="cn-standard",
        kind="tender",
        estimated_value=budget,
        cpv_primary=cpv,
        deadline=deadline,
    )


def _grades(extracted, truth):
    return {g.field: g.grade for g in grade_notice(extracted, truth)}


def test_exact_match_all_fields():
    truth = _tender(budget=100000.0)
    got = ExtractedFields(budget=100000.0, cpv_primary="72000000", deadline=dt.date(2024, 10, 1))
    assert _grades(got, truth) == {
        "budget": Grade.MATCH,
        "cpv_primary": Grade.MATCH,
        "deadline": Grade.MATCH,
    }


def test_budget_within_tolerance_matches():
    truth = _tender(budget=100000.0)
    got = ExtractedFields(budget=100000.0 + 0.005 * 100000.0, cpv_primary="72000000")
    assert _grades(got, truth)["budget"] == Grade.MATCH


def test_budget_outside_tolerance_mismatches():
    truth = _tender(budget=100000.0)
    got = ExtractedFields(budget=110000.0, cpv_primary="72000000")
    assert _grades(got, truth)["budget"] == Grade.MISMATCH


def test_missed_field_is_mismatch_not_skipped():
    truth = _tender(budget=100000.0)
    got = ExtractedFields(budget=None, cpv_primary="72000000")  # extractor missed the budget
    assert _grades(got, truth)["budget"] == Grade.MISMATCH


def test_absent_ground_truth_is_not_graded():
    truth = _tender(budget=None)  # XML had no budget
    got = ExtractedFields(budget=999.0, cpv_primary="72000000")
    # Even though the extractor produced a value, we cannot check it -> NO_GROUND_TRUTH.
    assert _grades(got, truth)["budget"] == Grade.NO_GROUND_TRUTH


def test_wrong_cpv_and_deadline_mismatch():
    truth = _tender(cpv="72000000", deadline=dt.date(2024, 10, 1))
    got = ExtractedFields(cpv_primary="30000000", deadline=dt.date(2024, 10, 2))
    g = _grades(got, truth)
    assert g["cpv_primary"] == Grade.MISMATCH
    assert g["deadline"] == Grade.MISMATCH


def test_score_excludes_no_ground_truth_from_accuracy():
    # Two notices: one fully gradable (all correct), one with no budget truth.
    t1 = _tender(budget=100000.0)
    e1 = ExtractedFields(budget=100000.0, cpv_primary="72000000", deadline=dt.date(2024, 10, 1))
    t2 = _tender(budget=None)
    e2 = ExtractedFields(budget=None, cpv_primary="72000000", deadline=dt.date(2024, 10, 1))

    card = score([(e1, t1), (e2, t2)])
    budget = card.per_field["budget"]
    assert budget == {"match": 1, "mismatch": 0, "no_ground_truth": 1, "accuracy": 1.0}
    # cpv + deadline: 2 matches each; budget: 1 match. Overall = 5/5 gradable.
    assert card.overall_accuracy == 1.0


def test_scorecard_format_is_readable():
    card = score([(ExtractedFields(cpv_primary="72000000"), _tender(budget=None, deadline=None))])
    out = card.format()
    assert "cpv_primary" in out and "overall" in out
