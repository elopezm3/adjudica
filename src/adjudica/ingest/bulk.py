"""Bulk, incremental ingestion over date windows — the rate-friendly path.

Per-procedure backfill (resolve.backfill_tenders_for_awards) makes one API call
per procedure and trips TED's rate limit at scale. This module instead pulls
whole date windows of tenders and awards in a few paginated calls, then links
them locally by procedure_id — the same answer-key table, a fraction of the calls.

Incremental via a publication-date watermark: each run fetches only from the
latest date already stored. Idempotent upserts make the overlapping boundary day
harmless. See docs/findings/ted-eforms-boundary.md for the valid date window.
"""

from __future__ import annotations

import argparse
import datetime as dt
from pathlib import Path

import duckdb

from adjudica.ingest import store
from adjudica.ingest.normalize import normalize_notice
from adjudica.ingest.resolve import build_links, link_stats
from adjudica.ingest.run import build_query
from adjudica.ingest.ted_client import TedClient

_KIND_TO_NOTICE_TYPE = {"tender": "cn-standard", "award": "can-standard"}
INGEST_KINDS = ("tender", "award")


def _yyyymmdd(d: dt.date) -> str:
    return d.strftime("%Y%m%d")


def watermark(con: duckdb.DuckDBPyConnection, kind: str) -> dt.date | None:
    """Latest publication_date already stored for a kind — the incremental cursor."""
    row = con.execute("SELECT max(publication_date) FROM notices WHERE kind = ?", [kind]).fetchone()
    return row[0] if row and row[0] is not None else None


def ingest_range(
    con: duckdb.DuckDBPyConnection,
    *,
    country: str,
    kind: str,
    date_from: str,
    date_to: str,
    client: TedClient | None = None,
) -> int:
    """Fully paginate one kind over a window and upsert. Returns count written."""
    query = build_query(country, _KIND_TO_NOTICE_TYPE[kind], date_from, date_to)
    owns = client is None
    client = client or TedClient()
    try:
        records = (normalize_notice(raw) for raw in client.iter_notices(query))
        return store.upsert_notices(con, records)
    finally:
        if owns:
            client.close()


def build_dataset(
    con: duckdb.DuckDBPyConnection,
    *,
    country: str,
    date_from: str,
    date_to: str,
    kinds: tuple[str, ...] = INGEST_KINDS,
    client: TedClient | None = None,
) -> dict:
    """Ingest tenders + awards over a window (bulk), then (re)build the linked table."""
    owns = client is None
    client = client or TedClient()
    try:
        counts = {
            kind: ingest_range(
                con, country=country, kind=kind, date_from=date_from, date_to=date_to, client=client
            )
            for kind in kinds
        }
    finally:
        if owns:
            client.close()
    linked = build_links(con)
    return {"ingested": counts, "linked": linked, "stats": link_stats(con)}


def main() -> None:
    parser = argparse.ArgumentParser(description="Bulk/incremental TED ingestion + linking.")
    parser.add_argument("--country", default="ESP")
    parser.add_argument("--from", dest="date_from", help="YYYYMMDD; omitted with --incremental")
    parser.add_argument("--to", dest="date_to", required=True, help="YYYYMMDD")
    parser.add_argument(
        "--incremental",
        action="store_true",
        help="Start from the latest stored publication-date instead of --from.",
    )
    parser.add_argument("--db", default="data/adjudica.duckdb")
    args = parser.parse_args()

    Path(args.db).parent.mkdir(parents=True, exist_ok=True)
    con = store.connect(args.db)
    try:
        date_from = args.date_from
        if args.incremental:
            marks = [w for k in INGEST_KINDS if (w := watermark(con, k))]
            if marks:
                date_from = _yyyymmdd(min(marks))  # re-pull from the earliest cursor
        if not date_from:
            raise SystemExit("Provide --from, or --incremental once the DB has data.")

        result = build_dataset(con, country=args.country, date_from=date_from, date_to=args.date_to)
        print(
            f"Ingested {result['ingested']} ({args.country} {date_from}-{args.date_to}). "
            f"Linked {result['linked']} tenders. Outcomes: {result['stats']['by_outcome']}. "
            f"Median award lag: {result['stats']['median_lag_days']} days."
        )
    finally:
        con.close()


if __name__ == "__main__":
    main()
