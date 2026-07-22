"""Ingest the PLACSP feed into DuckDB.

uv run python -m adjudica.placsp.ingest --db data/adjudica.duckdb --max 500
"""

from __future__ import annotations

import argparse
from pathlib import Path

from adjudica.placsp import store
from adjudica.placsp.documents import new_client
from adjudica.placsp.feed import iter_feed


def main() -> None:
    parser = argparse.ArgumentParser(description="Ingest PLACSP tenders into DuckDB.")
    parser.add_argument("--db", default="data/adjudica.duckdb")
    parser.add_argument("--max", dest="max_entries", type=int, default=None)
    args = parser.parse_args()

    Path(args.db).parent.mkdir(parents=True, exist_ok=True)
    con = store.connect(args.db)
    http = new_client()
    try:
        written = store.upsert_entries(con, iter_feed(http, max_entries=args.max_entries))
        with_docs = con.execute(
            "SELECT count(*) FROM placsp_tenders WHERE len(doc_uris) > 0"
        ).fetchone()[0]
        print(
            f"Ingested {written} PLACSP tenders. "
            f"DB holds {store.count(con)}, {with_docs} with pliego documents."
        )
    finally:
        http.close()
        con.close()


if __name__ == "__main__":
    main()
