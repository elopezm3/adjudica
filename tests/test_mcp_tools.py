"""MCP tool tests — plain functions over an in-memory DuckDB, offline."""

import datetime as dt

import pytest

from adjudica.extract.schema import ExtractedFields
from adjudica.ingest import store as ted_store
from adjudica.ingest.models import NoticeRecord
from adjudica.mcp_server import tools
from adjudica.placsp import store as placsp_store
from adjudica.placsp.models import PlacspDocument, PlacspEntry
from adjudica.qualify.profile import CompanyProfile

LIMPIASUR = CompanyProfile(
    name="LimpiaSur S.L.",
    cpv_prefixes=["9091"],
    annual_turnover=900_000,
    certifications=["ISO 9001"],
)


def _entry(entry_id, cpv, budget, docs=True):
    return PlacspEntry(
        entry_id=entry_id,
        expediente=f"EXP-{entry_id}",
        title=f"Tender {entry_id}",
        budget=budget,
        cpv_primary=cpv,
        deadline=dt.date(2026, 8, 10),
        documents=(
            [PlacspDocument(kind="legal", name="PCAP.pdf", uri=f"https://x/{entry_id}")]
            if docs
            else []
        ),
    )


@pytest.fixture
def con():
    c = placsp_store.connect(":memory:")
    placsp_store.upsert_entries(
        c,
        [
            _entry("t1", "90911200", 331_252.82),
            _entry("t2", "90911200", 12_000_000),
            _entry("t3", "72000000", 450_000),
        ],
    )
    return c


def test_search_filters_by_cpv_family(con):
    got = tools.search_tenders(con, cpv_prefix="9091")
    assert {t["tender_id"] for t in got} == {"t1", "t2"}


def test_search_filters_by_budget_and_orders_desc(con):
    got = tools.search_tenders(con, max_budget=1_000_000)
    assert [t["tender_id"] for t in got] == ["t3", "t1"]  # 450k then 331k


def test_search_respects_limit(con):
    assert len(tools.search_tenders(con, limit=1)) == 1


def test_get_tender_includes_document_links(con):
    detail = tools.get_tender(con, "t1")
    assert detail["expediente"] == "EXP-t1"
    assert detail["document_links"][0]["uri"] == "https://x/t1"


def test_get_tender_missing_returns_none(con):
    assert tools.get_tender(con, "nope") is None


def test_eligibility_uses_stored_budget_and_cpv(con):
    # Out-of-scope CPV must be caught from stored data alone.
    out = tools.check_tender_eligibility(con, "t3", profile=LIMPIASUR)
    assert out["verdict"] == "not_eligible"
    assert any("outside" in r for r in out["blocking_reasons"])


def test_eligibility_is_unknown_without_extracted_requirements(con):
    # No pliego requirements supplied -> cannot verify solvency/certs -> UNKNOWN.
    out = tools.check_tender_eligibility(con, "t1", profile=LIMPIASUR)
    assert out["verdict"] == "unknown"
    assert out["confirm_by_hand"]


def test_eligibility_with_requirements_can_reach_eligible(con):
    reqs = ExtractedFields(solvency_turnover_required=250_000, required_certifications=["ISO 9001"])
    out = tools.check_tender_eligibility(con, "t1", profile=LIMPIASUR, requirements=reqs)
    assert out["verdict"] == "eligible"
    assert out["blocking_reasons"] == []


def test_eligibility_reports_all_rules(con):
    out = tools.check_tender_eligibility(con, "t1", profile=LIMPIASUR)
    assert {c["rule"] for c in out["checks"]} == {
        "scope",
        "solvency",
        "certifications",
        "capacity",
    }


def test_past_awards_without_ted_table_is_graceful(con):
    out = tools.past_awards_for_cpv(con, "9091")
    assert out["awards"] == []
    assert "note" in out


def test_past_awards_summarises_outcomes(con):
    ted_store.ensure_schema(con)  # TED notices live alongside PLACSP tenders in one file
    ted_store.upsert_notices(
        con,
        [
            NoticeRecord(
                publication_number="a1",
                notice_type="can-standard",
                kind="award",
                cpv_primary="90911200",
                title="Cleaning award",
                result_value=300_000.0,
                winner_names=["ACME"],
                winner_selection_status=["selec-w"],
            ),
            NoticeRecord(
                publication_number="a2",
                notice_type="can-standard",
                kind="award",
                cpv_primary="90911200",
                winner_selection_status=["clos-nw"],
            ),
        ],
    )
    out = tools.past_awards_for_cpv(con, "9091")
    assert out["outcome_counts"] == {"awarded": 1, "desierto": 1}
    assert out["awards"][0]["winners"] == ["ACME"]
