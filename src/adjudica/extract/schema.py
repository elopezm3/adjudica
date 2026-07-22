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
    """Fields an extractor returns for one tender. All optional — absence is a real answer.

    The first three have XML ground truth and are auto-graded. The rest exist only in the
    PDF prose and drive the actual bid decision — they are extracted but NOT auto-graded
    (see evals.extraction.GRADED_FIELDS), and get a hand-labeled sample later.
    """

    # --- auto-gradable against the CODICE/eForms XML ---
    budget: float | None = None
    cpv_primary: str | None = None
    deadline: dt.date | None = None

    # --- product fields: PDF-only, no XML answer key ---
    # Minimum annual turnover ("volumen anual de negocios") required to bid.
    solvency_turnover_required: float | None = None
    # Certifications / classifications demanded (e.g. "ISO 9001", "Clasificación O-6-2").
    required_certifications: list[str] = []
    # Share of the award score decided by price, 0-100. A high value means a price race
    # an incumbent usually wins; a low value means quality can beat them.
    price_weight_pct: float | None = None
    # Number of lots the contract is split into.
    lots: int | None = None
