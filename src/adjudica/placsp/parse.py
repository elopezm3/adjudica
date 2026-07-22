"""Parse the PLACSP ATOM feed's CODICE XML into typed entries.

Pure and offline. CODICE uses cbc:/cac: namespaces; we match by local-name so we don't
hard-code namespace URIs (which vary across CODICE versions). Scoped lookups matter: an
entry has many EndDate / Name / amount elements, so budget/deadline/title are read from
inside their specific parent block, not the first match anywhere in the entry.
"""

from __future__ import annotations

import datetime as dt
from collections.abc import Iterator

from lxml import etree

from adjudica.ingest.models import NoticeRecord
from adjudica.placsp.models import PlacspDocument, PlacspEntry

_DOC_TAGS: tuple[tuple[str, str], ...] = (
    ("legal", "LegalDocumentReference"),
    ("technical", "TechnicalDocumentReference"),
)


def _first(el, localname: str):
    found = el.xpath(".//*[local-name()=$n]", n=localname)
    return found[0] if found else None


def _first_text(el, localname: str) -> str | None:
    node = _first(el, localname) if el is not None else None
    if node is not None and node.text and node.text.strip():
        return node.text.strip()
    return None


def _to_float(value: str | None) -> float | None:
    try:
        return float(value) if value is not None else None
    except ValueError:
        return None


def _to_date(value: str | None) -> dt.date | None:
    if not value or len(value) < 10:
        return None
    try:
        return dt.date.fromisoformat(value[:10])
    except ValueError:
        return None


def parse_entry(entry) -> PlacspEntry:
    """Parse one <entry> element into a PlacspEntry."""
    budget_block = _first(entry, "BudgetAmount")
    budget = _to_float(
        _first_text(budget_block, "TaxExclusiveAmount")
        or _first_text(budget_block, "EstimatedOverallContractAmount")
    )

    deadline = _to_date(_first_text(_first(entry, "TenderSubmissionDeadlinePeriod"), "EndDate"))
    title = _first_text(_first(entry, "ProcurementProject"), "Name")

    documents: list[PlacspDocument] = []
    for kind, tag in _DOC_TAGS:
        for ref in entry.xpath(".//*[local-name()=$n]", n=tag):
            uri = _first_text(ref, "URI")
            if uri:
                documents.append(PlacspDocument(kind=kind, name=_first_text(ref, "ID"), uri=uri))

    return PlacspEntry(
        entry_id=_first_text(entry, "id") or "",
        expediente=_first_text(entry, "ContractFolderID"),
        title=title,
        budget=budget,
        cpv_primary=_first_text(entry, "ItemClassificationCode"),
        deadline=deadline,
        documents=documents,
    )


def iter_entries(atom_bytes: bytes) -> Iterator[PlacspEntry]:
    """Yield PlacspEntry for every <entry> in an ATOM feed (pass raw bytes, not str)."""
    root = etree.fromstring(atom_bytes)
    for entry in root.xpath(".//*[local-name()='entry']"):
        yield parse_entry(entry)


def to_notice(entry: PlacspEntry) -> NoticeRecord:
    """Adapt a PLACSP entry to a NoticeRecord so the extraction harness can grade it."""
    return NoticeRecord(
        publication_number=entry.entry_id or entry.expediente or "unknown",
        notice_type="cn-standard",
        kind="tender",
        cpv=[entry.cpv_primary] if entry.cpv_primary else [],
        cpv_primary=entry.cpv_primary,
        title=entry.title,
        estimated_value=entry.budget,
        deadline=entry.deadline,
    )
