"""Bulk/incremental ingestion tests — offline via MockTransport."""

import datetime as dt
import json

import httpx

from adjudica.ingest import bulk, store
from adjudica.ingest.ted_client import TedClient


def _notice(pub, ntype, pid, date):
    return {
        "publication-number": pub,
        "notice-type": ntype,
        "procedure-identifier": pid,
        "publication-date": f"{date}+01:00",
        "winner-selection-status": ["selec-w"] if ntype == "can-standard" else None,
    }


def _mock_client(by_notice_type):
    """A client whose responses depend on which notice-type the query asks for."""

    def handler(request: httpx.Request) -> httpx.Response:
        query = json.loads(request.read())["query"]
        ntype = "can-standard" if "can-standard" in query else "cn-standard"
        return httpx.Response(
            200,
            json={
                "notices": by_notice_type.get(ntype, []),
                "totalNoticeCount": 0,
                "iterationNextToken": None,
            },
        )

    return TedClient(httpx.Client(transport=httpx.MockTransport(handler)), min_interval_s=0)


def test_build_dataset_ingests_both_kinds_and_links():
    client = _mock_client(
        {
            "cn-standard": [_notice("T-1", "cn-standard", "p1", "2024-09-01")],
            "can-standard": [_notice("W-1", "can-standard", "p1", "2025-02-01")],
        }
    )
    con = store.connect(":memory:")
    result = bulk.build_dataset(
        con, country="ESP", date_from="20240101", date_to="20251231", client=client
    )
    client.close()

    assert result["ingested"] == {"tender": 1, "award": 1}
    assert result["linked"] == 1
    assert result["stats"]["by_outcome"] == {"awarded": 1}
    # The tender and award were joined locally — no per-procedure calls needed.
    row = con.execute("SELECT tender_pub, award_pub, outcome FROM procedure_links").fetchone()
    assert row == ("T-1", "W-1", "awarded")


def test_watermark_returns_latest_date_per_kind():
    con = store.connect(":memory:")
    client = _mock_client(
        {
            "cn-standard": [
                _notice("T-1", "cn-standard", "p1", "2024-09-01"),
                _notice("T-2", "cn-standard", "p2", "2024-09-15"),
            ],
            "can-standard": [],
        }
    )
    bulk.build_dataset(con, country="ESP", date_from="20240101", date_to="20241231", client=client)
    client.close()
    assert bulk.watermark(con, "tender") == dt.date(2024, 9, 15)
    assert bulk.watermark(con, "award") is None  # nothing ingested for this kind


def test_query_routes_by_notice_type():
    # Guards the mock's own routing so the other tests mean what they claim.
    client = _mock_client({"cn-standard": [_notice("T", "cn-standard", "p", "2024-09-01")]})
    con = store.connect(":memory:")
    n_tender = bulk.ingest_range(
        con, country="ESP", kind="tender", date_from="20240101", date_to="20241231", client=client
    )
    n_award = bulk.ingest_range(
        con, country="ESP", kind="award", date_from="20240101", date_to="20241231", client=client
    )
    client.close()
    assert n_tender == 1
    assert n_award == 0
