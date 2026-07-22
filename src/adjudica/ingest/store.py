"""DuckDB persistence for normalized notices.

One table, `notices`, keyed by publication_number. Upserts are idempotent so re-running
an ingest window is safe. List fields (cpv, winners, values) use native DuckDB LIST types.
"""

from __future__ import annotations

from collections.abc import Iterable
from pathlib import Path

import duckdb

from adjudica.ingest.models import NoticeRecord

_SCHEMA = """
CREATE TABLE IF NOT EXISTS notices (
    publication_number  VARCHAR PRIMARY KEY,
    notice_type         VARCHAR,
    kind                VARCHAR,
    procedure_id        VARCHAR,
    is_eforms           BOOLEAN,
    cpv                 VARCHAR[],
    cpv_primary         VARCHAR,
    buyer_name          VARCHAR,
    title               VARCHAR,
    publication_date    DATE,
    deadline            DATE,
    estimated_value     DOUBLE,
    winner_names        VARCHAR[],
    winner_selection_status VARCHAR[],
    award_outcome       VARCHAR,
    tender_values       DOUBLE[],
    result_value        DOUBLE
);
"""

_COLUMNS = (
    "publication_number",
    "notice_type",
    "kind",
    "procedure_id",
    "is_eforms",
    "cpv",
    "cpv_primary",
    "buyer_name",
    "title",
    "publication_date",
    "deadline",
    "estimated_value",
    "winner_names",
    "winner_selection_status",
    "award_outcome",
    "tender_values",
    "result_value",
)


def connect(path: str | Path = ":memory:") -> duckdb.DuckDBPyConnection:
    """Open a DuckDB connection and ensure the schema exists."""
    con = duckdb.connect(str(path))
    ensure_schema(con)
    return con


def ensure_schema(con: duckdb.DuckDBPyConnection) -> None:
    """Create the notices table if absent. Idempotent; safe on a shared connection."""
    con.execute(_SCHEMA)


def _row(rec: NoticeRecord) -> tuple:
    return (
        rec.publication_number,
        rec.notice_type,
        rec.kind,
        rec.procedure_id,
        rec.is_eforms,
        rec.cpv,
        rec.cpv_primary,
        rec.buyer_name,
        rec.title,
        rec.publication_date,
        rec.deadline,
        rec.estimated_value,
        rec.winner_names,
        rec.winner_selection_status,
        rec.award_outcome,
        rec.tender_values,
        rec.result_value,
    )


def upsert_notices(con: duckdb.DuckDBPyConnection, records: Iterable[NoticeRecord]) -> int:
    """Insert or replace notices by publication_number. Returns the count written."""
    rows = [_row(r) for r in records]
    if not rows:
        return 0
    placeholders = ", ".join(["?"] * len(_COLUMNS))
    con.executemany(
        f"INSERT OR REPLACE INTO notices ({', '.join(_COLUMNS)}) VALUES ({placeholders})",
        rows,
    )
    return len(rows)


def eforms_coverage(con: duckdb.DuckDBPyConnection) -> dict[str, float]:
    """Fraction of ingested notices that are eForms, overall and by kind — a data check."""
    total = con.execute("SELECT count(*) FROM notices").fetchone()[0]
    eforms = con.execute("SELECT count(*) FROM notices WHERE is_eforms").fetchone()[0]
    return {
        "total": total,
        "eforms": eforms,
        "eforms_fraction": (eforms / total) if total else 0.0,
    }
