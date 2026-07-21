"""Resolver tests — link-building SQL and procedure backfill (offline)."""

import datetime as dt

import httpx

from adjudica.ingest import resolve, store
from adjudica.ingest.models import NoticeRecord
from adjudica.ingest.ted_client import TedClient


def _tender(pub, pid, date):
    return NoticeRecord(
        publication_number=pub,
        notice_type="cn-standard",
        kind="tender",
        procedure_id=pid,
        publication_date=date,
    )


def _award(pub, pid, date, outcome_status):
    return NoticeRecord(
        publication_number=pub,
        notice_type="can-standard",
        kind="award",
        procedure_id=pid,
        publication_date=date,
        winner_selection_status=outcome_status,
    )


def test_build_links_pairs_tender_to_award_with_outcome_and_lag():
    con = store.connect(":memory:")
    store.upsert_notices(
        con,
        [
            _tender("T-A", "pid-A", dt.date(2024, 9, 1)),
            _award("W-A", "pid-A", dt.date(2025, 3, 1), ["selec-w"]),
        ],
    )
    resolve.build_links(con)
    row = con.execute(
        "SELECT tender_pub, award_pub, outcome, lag_days FROM procedure_links"
    ).fetchone()
    assert row == ("T-A", "W-A", "awarded", 181)


def test_tender_without_award_is_unknown_not_desierto():
    con = store.connect(":memory:")
    store.upsert_notices(con, [_tender("T-B", "pid-B", dt.date(2024, 10, 1))])
    resolve.build_links(con)
    outcome, lag = con.execute(
        "SELECT outcome, lag_days FROM procedure_links WHERE procedure_id = 'pid-B'"
    ).fetchone()
    assert outcome == "unknown"  # crucial: not-yet-awarded is distinct from desierto
    assert lag is None


def test_desierto_outcome_propagates():
    con = store.connect(":memory:")
    store.upsert_notices(
        con,
        [
            _tender("T-C", "pid-C", dt.date(2024, 9, 1)),
            _award("W-C", "pid-C", dt.date(2025, 1, 1), ["clos-nw"]),
        ],
    )
    resolve.build_links(con)
    outcome = con.execute(
        "SELECT outcome FROM procedure_links WHERE procedure_id = 'pid-C'"
    ).fetchone()[0]
    assert outcome == "desierto"


def test_link_stats_counts_by_outcome():
    con = store.connect(":memory:")
    store.upsert_notices(
        con,
        [
            _tender("T1", "p1", dt.date(2024, 9, 1)),
            _award("W1", "p1", dt.date(2025, 1, 1), ["selec-w"]),
            _tender("T2", "p2", dt.date(2024, 9, 1)),
            _award("W2", "p2", dt.date(2025, 1, 1), ["clos-nw"]),
            _tender("T3", "p3", dt.date(2024, 9, 1)),  # no award -> unknown
        ],
    )
    resolve.build_links(con)
    stats = resolve.link_stats(con)
    assert stats["by_outcome"] == {"awarded": 1, "desierto": 1, "unknown": 1}


def test_backfill_fetches_each_award_procedure_once():
    # An award is in the DB; backfill should query its procedure and pull in the tender.
    con = store.connect(":memory:")
    store.upsert_notices(con, [_award("W-9", "pid-9", dt.date(2025, 2, 1), ["selec-w"])])

    calls: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        import json

        calls.append(json.loads(request.read())["query"])
        return httpx.Response(
            200,
            json={
                "notices": [
                    {
                        "publication-number": "T-9",
                        "notice-type": "cn-standard",
                        "procedure-identifier": "pid-9",
                        "publication-date": "2024-09-01+02:00",
                    }
                ],
                "totalNoticeCount": 1,
                "iterationNextToken": None,
            },
        )

    client = TedClient(httpx.Client(transport=httpx.MockTransport(handler)), min_interval_s=0)
    result = resolve.backfill_tenders_for_awards(con, client)
    client.close()

    assert result["procedures"] == 1
    assert result["notices_upserted"] == 1
    assert calls == ["procedure-identifier=pid-9"]
    # The tender is now present, so a link can be built.
    resolve.build_links(con)
    assert con.execute("SELECT tender_pub FROM procedure_links").fetchone()[0] == "T-9"
