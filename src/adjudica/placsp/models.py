"""Typed records for a parsed PLACSP feed entry."""

from __future__ import annotations

import datetime as dt
from typing import Literal

from pydantic import BaseModel

DocumentKind = Literal["legal", "technical"]  # legal = PCAP, technical = PPT/proyecto


class PlacspDocument(BaseModel):
    """One document reference on a tender — a direct GetDocumentByIdServlet link."""

    kind: DocumentKind
    name: str | None = None  # e.g. "PCAP.pdf"
    uri: str


class PlacspEntry(BaseModel):
    """One tender from the PLACSP syndication feed, with ground-truth fields + docs."""

    entry_id: str
    expediente: str | None = None  # cbc:ContractFolderID (the Spanish file number)
    title: str | None = None
    # Ground truth (from the CODICE XML) for grading extraction from the PDF:
    budget: float | None = None  # presupuesto base sin IVA (TaxExclusiveAmount)
    cpv_primary: str | None = None
    deadline: dt.date | None = None
    documents: list[PlacspDocument] = []

    @property
    def legal_documents(self) -> list[PlacspDocument]:
        """PCAP references — the administrative pliego, where requirements live."""
        return [d for d in self.documents if d.kind == "legal"]
