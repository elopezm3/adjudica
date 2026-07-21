"""Link tenders to their awards — build the backtest answer key.

A procurement procedure publishes a tender notice (cn) and, months later, an award
notice (can), both carrying the same procedure-identifier. This module:

1. backfill_tenders_for_awards: for each award already in the DB, fetch its procedure's
   other notices from TED (by procedure-identifier) and store them — pulling in the tenders.
2. build_links: join tenders to awards per procedure into `procedure_links`, the table the
   Phase-3 backtest grades against.

Outcome is three-state and the distinction is load-bearing (see CLAUDE.md constraint 2):
    awarded   — the award selected a winner
    desierto  — the award closed with no winner
    unknown   — no award notice yet (NOT the same as desierto)
"""

from __future__ import annotations

import argparse
from pathlib import Path

import duckdb

from adjudica.ingest import store
from adjudica.ingest.normalize import normalize_notice
from adjudica.ingest.ted_client import TedClient

_LINKS_SQL = """
CREATE OR REPLACE TABLE procedure_links AS
WITH tenders AS (
    SELECT
        procedure_id,
        arg_min(publication_number, publication_date) AS tender_pub,
        min(publication_date)                         AS tender_date
    FROM notices
    WHERE kind = 'tender' AND procedure_id IS NOT NULL
    GROUP BY procedure_id
),
awards AS (
    SELECT
        procedure_id,
        arg_max(publication_number, publication_date) AS award_pub,
        max(publication_date)                         AS award_date,
        arg_max(award_outcome, publication_date)      AS outcome,
        arg_max(result_value, publication_date)       AS result_value
    FROM notices
    WHERE kind = 'award' AND procedure_id IS NOT NULL
    GROUP BY procedure_id
)
SELECT
    t.procedure_id,
    t.tender_pub,
    t.tender_date,
    a.award_pub,
    a.award_date,
    COALESCE(a.outcome, 'unknown')                        AS outcome,
    a.result_value,
    date_diff('day', t.tender_date, a.award_date)         AS lag_days
FROM tenders t
LEFT JOIN awards a USING (procedure_id);
"""


def fetch_procedure(client: TedClient, procedure_id: str) -> list[dict]:
    """All notices belonging to one procedure, via procedure-identifier query."""
    return list(client.iter_notices(f"procedure-identifier={procedure_id}"))


def backfill_tenders_for_awards(
    con: duckdb.DuckDBPyConnection,
    client: TedClient | None = None,
    *,
    max_procedures: int | None = None,
) -> dict[str, int]:
    """Fetch and store the notices of every award's procedure. One API call per procedure."""
    pids = [
        r[0]
        for r in con.execute(
            "SELECT DISTINCT procedure_id FROM notices "
            "WHERE kind = 'award' AND procedure_id IS NOT NULL"
        ).fetchall()
    ]
    if max_procedures is not None:
        pids = pids[:max_procedures]

    owns = client is None
    client = client or TedClient()
    upserted = 0
    try:
        for pid in pids:
            records = [normalize_notice(r) for r in fetch_procedure(client, pid)]
            upserted += store.upsert_notices(con, records)
    finally:
        if owns:
            client.close()
    return {"procedures": len(pids), "notices_upserted": upserted}


def build_links(con: duckdb.DuckDBPyConnection) -> int:
    """(Re)build the procedure_links table. Returns the number of linked tenders."""
    con.execute(_LINKS_SQL)
    return con.execute("SELECT count(*) FROM procedure_links").fetchone()[0]


def link_stats(con: duckdb.DuckDBPyConnection) -> dict:
    """Outcome breakdown and median award lag over the linked table — a health check."""
    by_outcome = dict(
        con.execute(
            "SELECT outcome, count(*) FROM procedure_links GROUP BY outcome ORDER BY outcome"
        ).fetchall()
    )
    median_lag = con.execute(
        "SELECT median(lag_days) FROM procedure_links WHERE lag_days IS NOT NULL"
    ).fetchone()[0]
    return {"by_outcome": by_outcome, "median_lag_days": median_lag}


def main() -> None:
    parser = argparse.ArgumentParser(description="Link tenders to awards in the DuckDB store.")
    parser.add_argument("--db", default="data/adjudica.duckdb")
    parser.add_argument("--max-procedures", type=int, default=None)
    args = parser.parse_args()

    if not Path(args.db).exists():
        raise SystemExit(
            f"No database at {args.db}. Ingest awards first (python -m adjudica.ingest)."
        )

    con = store.connect(args.db)
    try:
        back = backfill_tenders_for_awards(con, max_procedures=args.max_procedures)
        linked = build_links(con)
        stats = link_stats(con)
        print(
            f"Backfilled {back['procedures']} procedures "
            f"({back['notices_upserted']} notices upserted). "
            f"Linked {linked} tenders. Outcomes: {stats['by_outcome']}. "
            f"Median award lag: {stats['median_lag_days']} days."
        )
    finally:
        con.close()


if __name__ == "__main__":
    main()
