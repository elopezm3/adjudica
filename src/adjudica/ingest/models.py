"""Typed record for a normalized TED notice.

A NoticeRecord is the flattened, storage-ready form of one raw TED search hit.
Multilingual objects are collapsed to a single preferred-language string; arrays
are kept as lists. Only eForms notices carry `procedure_id` — legacy-schema notices
return it empty and are out of scope (see docs/findings/ted-eforms-boundary.md).
"""

from __future__ import annotations

import datetime as dt
from typing import Literal

from pydantic import BaseModel

NoticeKind = Literal["tender", "award", "other"]
# Outcome of an award notice, derived from winner-selection-status (per-lot).
AwardOutcome = Literal["awarded", "desierto"]


class NoticeRecord(BaseModel):
    """One normalized TED notice, ready to persist to DuckDB."""

    publication_number: str
    notice_type: str
    kind: NoticeKind
    # Links a tender to its award. Present only for eForms notices; None => legacy schema.
    procedure_id: str | None = None

    cpv: list[str] = []
    cpv_primary: str | None = None
    buyer_name: str | None = None
    title: str | None = None
    publication_date: dt.date | None = None

    # Tender-side fields.
    deadline: dt.date | None = None
    estimated_value: float | None = None

    # Award-side fields (populated for kind == "award").
    winner_names: list[str] = []
    # Per-lot winner-selection-status: "selec-w" (awarded) or "clos-nw" (desierto).
    winner_selection_status: list[str] = []
    tender_values: list[float] = []
    result_value: float | None = None

    @property
    def is_eforms(self) -> bool:
        return self.procedure_id is not None

    @property
    def award_outcome(self) -> AwardOutcome | None:
        """Classify an award by its lot statuses. None if not an award or status absent.

        A notice is "awarded" if ANY lot selected a winner, and "desierto" only if it has
        lot statuses and NONE selected one. Winner-name presence is deliberately ignored:
        a lot can be selec-w yet omit the winner's name (a real data gap, not a desierto).
        """
        if self.kind != "award" or not self.winner_selection_status:
            return None
        if any(s == "selec-w" for s in self.winner_selection_status):
            return "awarded"
        if all(s == "clos-nw" for s in self.winner_selection_status):
            return "desierto"
        return "awarded"  # mixed/other statuses: at least one lot resolved with a result
