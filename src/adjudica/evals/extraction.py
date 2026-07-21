"""Extraction eval harness — grade extracted fields against XML ground truth.

The eForms XML twin of each pliego is the answer key. For each gradable field we emit one
of three verdicts:

    MATCH            extracted value agrees with the XML truth
    MISMATCH         both exist but disagree, OR the XML has it and the extractor missed it
    NO_GROUND_TRUTH  the XML has no value, so we cannot grade this field here

Accuracy counts only MATCH / (MATCH + MISMATCH). NO_GROUND_TRUTH is never scored as right
or wrong — silently counting an ungradable field as correct would be the classic way to
fake a good eval number, which is exactly what this project exists not to do.
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Iterable
from dataclasses import dataclass
from enum import StrEnum
from typing import Any

from adjudica.extract.schema import ExtractedFields
from adjudica.ingest.models import NoticeRecord

GRADED_FIELDS = ("budget", "cpv_primary", "deadline")

# Budgets can differ slightly between the pliego prose and the XML (VAT, rounding, options).
# Allow a small relative tolerance so a correct read isn't marked wrong over a cent.
BUDGET_REL_TOLERANCE = 0.005
BUDGET_ABS_TOLERANCE = 0.01


class Grade(StrEnum):
    MATCH = "match"
    MISMATCH = "mismatch"
    NO_GROUND_TRUTH = "no_ground_truth"


@dataclass(frozen=True)
class FieldGrade:
    field: str
    extracted: Any
    truth: Any
    grade: Grade


def truth_fields(rec: NoticeRecord) -> ExtractedFields:
    """The answer key for one tender, projected onto the extractor's schema."""
    return ExtractedFields(
        budget=rec.estimated_value,
        cpv_primary=rec.cpv_primary,
        deadline=rec.deadline,
    )


def _budget_matches(got: float, truth: float) -> bool:
    return abs(got - truth) <= max(BUDGET_ABS_TOLERANCE, BUDGET_REL_TOLERANCE * abs(truth))


def _cpv_matches(got: str, truth: str) -> bool:
    return got.strip() == truth.strip()


def _field_matches(field: str, got: Any, truth: Any) -> bool:
    if field == "budget":
        return _budget_matches(got, truth)
    if field == "cpv_primary":
        return _cpv_matches(got, truth)
    return got == truth  # deadline: exact date equality


def grade_notice(extracted: ExtractedFields, truth: NoticeRecord) -> list[FieldGrade]:
    """Grade one extraction against its XML ground truth, field by field."""
    answer = truth_fields(truth)
    grades: list[FieldGrade] = []
    for field in GRADED_FIELDS:
        want = getattr(answer, field)
        got = getattr(extracted, field)
        if want is None:
            grade = Grade.NO_GROUND_TRUTH
        elif got is not None and _field_matches(field, got, want):
            grade = Grade.MATCH
        else:
            grade = Grade.MISMATCH  # disagreement or a miss (got is None)
        grades.append(FieldGrade(field=field, extracted=got, truth=want, grade=grade))
    return grades


@dataclass
class Scorecard:
    """Per-field accuracy over a set of graded extractions."""

    per_field: dict[str, dict[str, Any]]

    @property
    def overall_accuracy(self) -> float | None:
        match = sum(f["match"] for f in self.per_field.values())
        gradable = match + sum(f["mismatch"] for f in self.per_field.values())
        return match / gradable if gradable else None

    def format(self) -> str:
        lines = ["field         acc     match  miss  n/a"]
        for name, f in self.per_field.items():
            acc = "  --  " if f["accuracy"] is None else f"{f['accuracy']:.0%}".rjust(5)
            lines.append(
                f"{name:<13} {acc}  {f['match']:>5}  {f['mismatch']:>4}  {f['no_ground_truth']:>3}"
            )
        overall = self.overall_accuracy
        lines.append(f"overall       {'  --  ' if overall is None else f'{overall:.0%}'.rjust(5)}")
        return "\n".join(lines)


def score(pairs: Iterable[tuple[ExtractedFields, NoticeRecord]]) -> Scorecard:
    """Aggregate grades across (extraction, ground-truth) pairs into a Scorecard."""
    counts: dict[str, Counter] = {field: Counter() for field in GRADED_FIELDS}
    for extracted, truth in pairs:
        for fg in grade_notice(extracted, truth):
            counts[fg.field][fg.grade] += 1

    per_field: dict[str, dict[str, Any]] = {}
    for field, c in counts.items():
        match, mismatch = c[Grade.MATCH], c[Grade.MISMATCH]
        gradable = match + mismatch
        per_field[field] = {
            "match": match,
            "mismatch": mismatch,
            "no_ground_truth": c[Grade.NO_GROUND_TRUTH],
            "accuracy": (match / gradable) if gradable else None,
        }
    return Scorecard(per_field=per_field)
