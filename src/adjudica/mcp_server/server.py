"""FastMCP server exposing Adjudica's tools to Claude Desktop / Claude Code.

Run:
    uv run python -m adjudica.mcp_server.server            # uses data/adjudica.duckdb
    ADJUDICA_DB=/path/to.duckdb uv run python -m adjudica.mcp_server.server

Claude Desktop config (claude_desktop_config.json):
    {"mcpServers": {"adjudica": {
        "command": "uv",
        "args": ["run", "--directory", "/path/to/adjudica",
                 "python", "-m", "adjudica.mcp_server.server"]
    }}}
"""

from __future__ import annotations

import os
from typing import Any

from fastmcp import FastMCP

from adjudica.extract.schema import ExtractedFields
from adjudica.mcp_server import tools
from adjudica.placsp import store as placsp_store
from adjudica.qualify.profile import CompanyProfile

mcp = FastMCP("adjudica")

_DB_PATH = os.environ.get("ADJUDICA_DB", "data/adjudica.duckdb")
_con = None


def _db():
    """Lazy single connection — DuckDB files are opened on first tool call."""
    global _con
    if _con is None:
        _con = placsp_store.connect(_DB_PATH)
    return _con


@mcp.tool
def search_tenders(
    cpv_prefix: str | None = None,
    max_budget: float | None = None,
    min_budget: float | None = None,
    limit: int = 20,
) -> list[dict[str, Any]]:
    """Search published Spanish public tenders.

    cpv_prefix filters by CPV family (e.g. "9091" for building cleaning).
    Budgets are in euros. Returns the largest-budget matches first.
    """
    return tools.search_tenders(
        _db(), cpv_prefix=cpv_prefix, max_budget=max_budget, min_budget=min_budget, limit=limit
    )


@mcp.tool
def get_tender(tender_id: str) -> dict[str, Any] | None:
    """Full detail for one tender, including links to its pliego documents."""
    return tools.get_tender(_db(), tender_id)


@mcp.tool
def check_tender_eligibility(
    tender_id: str,
    company_name: str,
    cpv_prefixes: list[str],
    annual_turnover: float | None = None,
    certifications: list[str] | None = None,
    max_contract_value: float | None = None,
    solvency_turnover_required: float | None = None,
    required_certifications: list[str] | None = None,
) -> dict[str, Any] | None:
    """Decide whether a company can legally bid on a tender.

    Describe the company (CPV families, turnover, certifications). If you already know
    the pliego's requirements, pass solvency_turnover_required / required_certifications
    so those rules can be checked; otherwise they report UNVERIFIED and the verdict stays
    UNKNOWN rather than falsely claiming the company qualifies.
    """
    profile = CompanyProfile(
        name=company_name,
        cpv_prefixes=cpv_prefixes,
        annual_turnover=annual_turnover,
        certifications=certifications or [],
        max_contract_value=max_contract_value,
    )
    requirements = ExtractedFields(
        solvency_turnover_required=solvency_turnover_required,
        required_certifications=required_certifications or [],
    )
    return tools.check_tender_eligibility(
        _db(), tender_id, profile=profile, requirements=requirements
    )


@mcp.tool
def past_awards_for_cpv(cpv_prefix: str, limit: int = 10) -> dict[str, Any]:
    """What happened to comparable past contracts: award values, winners, desierto counts.

    Use this to judge whether a tender is winnable — e.g. whether one incumbent keeps
    winning this CPV family, and at what prices.
    """
    return tools.past_awards_for_cpv(_db(), cpv_prefix, limit=limit)


def main() -> None:
    mcp.run()


if __name__ == "__main__":
    main()
