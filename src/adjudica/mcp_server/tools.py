"""Tool implementations, as plain functions over a DuckDB connection.

Kept free of MCP imports so they can be tested directly. Every function returns plain
dicts/lists — JSON-friendly for the protocol, and readable when Claude relays them.
"""

from __future__ import annotations

from typing import Any

import duckdb

from adjudica.extract.schema import ExtractedFields
from adjudica.placsp import store as placsp_store
from adjudica.placsp.models import PlacspEntry
from adjudica.qualify.eligibility import check_eligibility
from adjudica.qualify.profile import CompanyProfile


def _tender_summary(entry: PlacspEntry) -> dict[str, Any]:
    return {
        "tender_id": entry.entry_id,
        "expediente": entry.expediente,
        "title": entry.title,
        "budget_eur": entry.budget,
        "cpv": entry.cpv_primary,
        "deadline": entry.deadline.isoformat() if entry.deadline else None,
        "documents": len(entry.documents),
    }


def search_tenders(
    con: duckdb.DuckDBPyConnection,
    *,
    cpv_prefix: str | None = None,
    max_budget: float | None = None,
    min_budget: float | None = None,
    limit: int = 20,
) -> list[dict[str, Any]]:
    """Find published tenders, optionally filtered by CPV family and budget range."""
    entries = placsp_store.search(
        con, cpv_prefix=cpv_prefix, max_budget=max_budget, min_budget=min_budget, limit=limit
    )
    return [_tender_summary(e) for e in entries]


def get_tender(con: duckdb.DuckDBPyConnection, tender_id: str) -> dict[str, Any] | None:
    """Full detail for one tender, including its pliego document links."""
    entry = placsp_store.get(con, tender_id)
    if entry is None:
        return None
    detail = _tender_summary(entry)
    detail["document_links"] = [
        {"kind": d.kind, "name": d.name, "uri": d.uri} for d in entry.documents
    ]
    return detail


def check_tender_eligibility(
    con: duckdb.DuckDBPyConnection,
    tender_id: str,
    *,
    profile: CompanyProfile,
    requirements: ExtractedFields | None = None,
) -> dict[str, Any] | None:
    """Can this company bid on this tender?

    Uses the structured fields we already hold (budget, CPV) plus, when supplied,
    requirements extracted from the pliego (turnover floor, certifications). Without
    those extracted requirements the solvency/certification rules report UNVERIFIED and
    the verdict stays UNKNOWN — deliberately, rather than guessing a clean 'eligible'.
    """
    entry = placsp_store.get(con, tender_id)
    if entry is None:
        return None

    fields = (requirements or ExtractedFields()).model_copy(
        update={"budget": entry.budget, "cpv_primary": entry.cpv_primary}
    )
    result = check_eligibility(profile, fields)
    return {
        "tender_id": entry.entry_id,
        "title": entry.title,
        "verdict": result.verdict.value,
        "blocking_reasons": result.blocking_reasons,
        "confirm_by_hand": result.unverified,
        "checks": [
            {"rule": c.rule, "outcome": c.outcome.value, "detail": c.detail} for c in result.checks
        ],
    }


def past_awards_for_cpv(
    con: duckdb.DuckDBPyConnection, cpv_prefix: str, *, limit: int = 10
) -> dict[str, Any]:
    """What happened to comparable past contracts — award values, winners, desierto rate.

    Reads the TED `notices` table (Phase-0 data). Returns an empty summary if that table
    hasn't been ingested yet rather than failing.
    """
    try:
        rows = con.execute(
            """
            SELECT publication_number, title, result_value, winner_names, award_outcome
            FROM notices
            WHERE kind = 'award' AND cpv_primary LIKE ?
            ORDER BY result_value DESC NULLS LAST
            LIMIT ?
            """,
            [f"{cpv_prefix}%", limit],
        ).fetchall()
        totals = con.execute(
            """
            SELECT award_outcome, count(*) FROM notices
            WHERE kind = 'award' AND cpv_primary LIKE ? AND award_outcome IS NOT NULL
            GROUP BY award_outcome
            """,
            [f"{cpv_prefix}%"],
        ).fetchall()
    except duckdb.CatalogException:
        return {
            "cpv_prefix": cpv_prefix,
            "awards": [],
            "outcome_counts": {},
            "note": "no TED award data ingested yet",
        }

    return {
        "cpv_prefix": cpv_prefix,
        "awards": [
            {
                "notice": pn,
                "title": title,
                "award_value_eur": value,
                "winners": winners or [],
                "outcome": outcome,
            }
            for pn, title, value, winners, outcome in rows
        ],
        "outcome_counts": dict(totals),
    }
