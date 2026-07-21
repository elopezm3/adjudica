"""The structured fields an extractor pulls from a pliego document.

Phase 1 grades only the subset that has *free* ground truth in the eForms XML twin of
the document: budget, primary CPV, and the bid deadline. Requirement fields that live
ONLY in the PDF prose (solvency thresholds, required certifications, award-criteria
weights) are extraction targets too, but they have no XML answer key, so they are graded
later against a hand-labeled sample — not by this auto-harness. Keeping the auto-gradable
set explicit is the honest move: we measure what we can check independently.
"""

from __future__ import annotations

import datetime as dt

from pydantic import BaseModel


class ExtractedFields(BaseModel):
    """Fields an extractor returns for one tender. All optional — absence is a real answer."""

    budget: float | None = None
    cpv_primary: str | None = None
    deadline: dt.date | None = None
