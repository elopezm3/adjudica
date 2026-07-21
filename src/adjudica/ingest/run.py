"""Ingest a TED query window into DuckDB.

CLI:
    uv run python -m adjudica.ingest --country ESP --kind tender \
        --from 20240901 --to 20240930 --db data/adjudica.duckdb --max 200

Defaults target the verified viable window (2024-H2+ eForms Spanish notices).
"""

from __future__ import annotations

import argparse
from pathlib import Path

from adjudica.ingest import store
from adjudica.ingest.normalize import normalize_notice
from adjudica.ingest.ted_client import TedClient

_KIND_TO_NOTICE_TYPE = {"tender": "cn-standard", "award": "can-standard"}


def build_query(country: str, notice_type: str, date_from: str, date_to: str) -> str:
    return (
        f"buyer-country={country} AND notice-type={notice_type} "
        f"AND publication-date>={date_from} AND publication-date<={date_to}"
    )


def ingest_window(
    con,
    *,
    country: str,
    kind: str,
    date_from: str,
    date_to: str,
    max_notices: int | None = None,
    client: TedClient | None = None,
) -> int:
    """Fetch one window from TED, normalize, and upsert into `con`. Returns count."""
    notice_type = _KIND_TO_NOTICE_TYPE[kind]
    query = build_query(country, notice_type, date_from, date_to)
    owns = client is None
    client = client or TedClient()
    try:
        records = (
            normalize_notice(raw) for raw in client.iter_notices(query, max_notices=max_notices)
        )
        return store.upsert_notices(con, records)
    finally:
        if owns:
            client.close()


def main() -> None:
    parser = argparse.ArgumentParser(description="Ingest a TED query window into DuckDB.")
    parser.add_argument("--country", default="ESP")
    parser.add_argument("--kind", choices=("tender", "award"), default="tender")
    parser.add_argument("--from", dest="date_from", required=True, help="YYYYMMDD")
    parser.add_argument("--to", dest="date_to", required=True, help="YYYYMMDD")
    parser.add_argument("--db", default="data/adjudica.duckdb")
    parser.add_argument("--max", dest="max_notices", type=int, default=None)
    args = parser.parse_args()

    Path(args.db).parent.mkdir(parents=True, exist_ok=True)
    con = store.connect(args.db)
    try:
        written = ingest_window(
            con,
            country=args.country,
            kind=args.kind,
            date_from=args.date_from,
            date_to=args.date_to,
            max_notices=args.max_notices,
        )
        cov = store.eforms_coverage(con)
        print(
            f"Ingested {written} {args.kind} notices "
            f"({args.country} {args.date_from}-{args.date_to}). "
            f"DB now holds {cov['total']} notices, "
            f"{cov['eforms_fraction']:.0%} eForms."
        )
    finally:
        con.close()


if __name__ == "__main__":
    main()
