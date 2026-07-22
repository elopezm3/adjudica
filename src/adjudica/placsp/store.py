"""DuckDB storage for PLACSP tenders — what the MCP server searches.

Separate table from TED `notices`: PLACSP entries carry the pliego document links and
are the live opportunity feed, while TED notices carry the award outcomes. They can share
one database file; `ensure_schema` is idempotent and safe to call on any connection.
"""

from __future__ import annotations

from collections.abc import Iterable
from pathlib import Path

import duckdb

from adjudica.placsp.models import PlacspDocument, PlacspEntry

_SCHEMA = """
CREATE TABLE IF NOT EXISTS placsp_tenders (
    entry_id      VARCHAR PRIMARY KEY,
    expediente    VARCHAR,
    title         VARCHAR,
    budget        DOUBLE,
    cpv_primary   VARCHAR,
    deadline      DATE,
    doc_kinds     VARCHAR[],
    doc_names     VARCHAR[],
    doc_uris      VARCHAR[]
);
"""

_COLUMNS = (
    "entry_id",
    "expediente",
    "title",
    "budget",
    "cpv_primary",
    "deadline",
    "doc_kinds",
    "doc_names",
    "doc_uris",
)


def connect(path: str | Path = ":memory:") -> duckdb.DuckDBPyConnection:
    con = duckdb.connect(str(path))
    ensure_schema(con)
    return con


def ensure_schema(con: duckdb.DuckDBPyConnection) -> None:
    con.execute(_SCHEMA)


def _row(entry: PlacspEntry) -> tuple:
    return (
        entry.entry_id,
        entry.expediente,
        entry.title,
        entry.budget,
        entry.cpv_primary,
        entry.deadline,
        [d.kind for d in entry.documents],
        [d.name or "" for d in entry.documents],
        [d.uri for d in entry.documents],
    )


def upsert_entries(con: duckdb.DuckDBPyConnection, entries: Iterable[PlacspEntry]) -> int:
    rows = [_row(e) for e in entries if e.entry_id]
    if not rows:
        return 0
    placeholders = ", ".join(["?"] * len(_COLUMNS))
    con.executemany(
        f"INSERT OR REPLACE INTO placsp_tenders ({', '.join(_COLUMNS)}) VALUES ({placeholders})",
        rows,
    )
    return len(rows)


def _to_entry(row: tuple) -> PlacspEntry:
    (entry_id, expediente, title, budget, cpv, deadline, kinds, names, uris) = row
    documents = [
        PlacspDocument(kind=k, name=n or None, uri=u)
        for k, n, u in zip(kinds or [], names or [], uris or [], strict=False)
    ]
    return PlacspEntry(
        entry_id=entry_id,
        expediente=expediente,
        title=title,
        budget=budget,
        cpv_primary=cpv,
        deadline=deadline,
        documents=documents,
    )


def search(
    con: duckdb.DuckDBPyConnection,
    *,
    cpv_prefix: str | None = None,
    max_budget: float | None = None,
    min_budget: float | None = None,
    limit: int = 20,
) -> list[PlacspEntry]:
    """Find tenders matching the filters, largest budget first."""
    where, params = [], []
    if cpv_prefix:
        where.append("cpv_primary LIKE ?")
        params.append(f"{cpv_prefix}%")
    if max_budget is not None:
        where.append("budget <= ?")
        params.append(max_budget)
    if min_budget is not None:
        where.append("budget >= ?")
        params.append(min_budget)
    clause = f"WHERE {' AND '.join(where)}" if where else ""
    params.append(limit)
    rows = con.execute(
        f"SELECT {', '.join(_COLUMNS)} FROM placsp_tenders {clause} "
        "ORDER BY budget DESC NULLS LAST LIMIT ?",
        params,
    ).fetchall()
    return [_to_entry(r) for r in rows]


def get(con: duckdb.DuckDBPyConnection, entry_id: str) -> PlacspEntry | None:
    row = con.execute(
        f"SELECT {', '.join(_COLUMNS)} FROM placsp_tenders WHERE entry_id = ?", [entry_id]
    ).fetchone()
    return _to_entry(row) if row else None


def count(con: duckdb.DuckDBPyConnection) -> int:
    return con.execute("SELECT count(*) FROM placsp_tenders").fetchone()[0]
