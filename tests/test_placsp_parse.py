"""PLACSP CODICE parsing tests against a real 2-entry feed fixture — offline."""

import datetime as dt
from pathlib import Path

import pytest

from adjudica.placsp.parse import iter_entries, parse_entry, to_notice

FIXTURE = Path(__file__).parent / "fixtures" / "placsp_sample.atom"


@pytest.fixture
def entries():
    return list(iter_entries(FIXTURE.read_bytes()))


def test_yields_all_entries(entries):
    assert len(entries) == 2


def test_first_entry_fields(entries):
    e = entries[0]
    assert e.expediente == "CON/2026/93"
    assert e.budget == 106971.94  # TaxExclusiveAmount (sin IVA), not TotalAmount 129436.05
    assert e.cpv_primary == "45212200"
    assert e.deadline == dt.date(2026, 8, 10)
    assert e.title and "vestuarios" in e.title.lower()
    assert e.entry_id.startswith("https://contrataciondelestado.es/")


def test_documents_have_direct_pliego_uris(entries):
    docs = entries[0].documents
    assert docs, "entry should reference at least one document"
    assert all("GetDocumentByIdServlet" in d.uri for d in docs)
    legal = entries[0].legal_documents
    assert legal and legal[0].kind == "legal"  # the PCAP


def test_budget_prefers_tax_exclusive_over_total():
    # Guards the sin-IVA choice: TotalAmount (con IVA) must not win.
    entry = next(iter_entries(FIXTURE.read_bytes()))
    assert entry.budget != 129436.05


def test_to_notice_maps_ground_truth(entries):
    rec = to_notice(entries[0])
    assert rec.kind == "tender"
    assert rec.estimated_value == 106971.94
    assert rec.cpv_primary == "45212200"
    assert rec.deadline == dt.date(2026, 8, 10)


def test_parse_entry_tolerates_missing_fields():
    from lxml import etree

    bare = etree.fromstring(b"<entry xmlns='http://www.w3.org/2005/Atom'><id>x</id></entry>")
    e = parse_entry(bare)
    assert e.entry_id == "x"
    assert e.budget is None and e.cpv_primary is None and e.deadline is None
    assert e.documents == []
