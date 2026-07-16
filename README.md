# Adjudica

A tender qualification agent for EU public procurement.

Given a company's capabilities profile, Adjudica scans published tenders (TED + Spain's
PLACSP), extracts the binding requirements from the tender specification documents
(*pliegos* — real-world messy PDFs, scans, and legacy Office files), decides which tenders
the company is eligible for and worth bidding on, and explains why — grounded in what
actually happened to comparable past tenders.

## Why this exists

Built eval-first as a Forward Deployed Engineering portfolio project. The domain was
chosen because it provides what most AI portfolio projects lack:

- **Authentically messy data** — native-text PDFs, image-only scans, `.docx`, and legacy
  binary `.doc` served with wrong content types, in Spanish and Galician.
- **A real, paid-for workflow** — commercial tender-finding/qualification software exists;
  this automates a job someone is paid to do.
- **Independent ground truth, twice over**:
  1. Every tender is published as structured eForms XML *and* as human documents. Fields
     present in both (budget, CPV, deadlines, lots…) grade PDF extraction objectively,
     with zero hand-labeling.
  2. Notices in a procedure share a procedure UUID, linking each tender to its **award
     notice** — awarded (value + winning bidder) or closed without a winner (*desierto*).
     Predictions grade against a published record we didn't author.

## Architecture (phased, eval-first)

| Phase | Deliverable | Ground truth |
|-------|-------------|--------------|
| 0 | Eval harness + data spine (TED/PLACSP 2023–2024 → DuckDB) | eForms XML fields |
| 1 | Extraction pipeline over messy documents (OCR fallback) | Phase 0 harness, per field |
| 2 | MCP server + qualification sub-agent | Eligibility vs. stated tender rules |
| 3 | Outcome-grounded backtest | Award notices (independent) |
| 4 | Engagement write-up + walkthrough | — |

The eval harness is built **before** the agent. That ordering is the project's thesis.

## Data sources

- **TED** — `api.ted.europa.eu/v3/notices/search` + bulk packages. Open, no key, CC BY 4.0.
- **PLACSP** — ATOM syndication feed only (the portal itself disallows crawling; the
  syndication channel exists for reuse). CODICE/UBL XML.

## Stack

Python 3.12 · uv · Polars · DuckDB · httpx · lxml · Claude API · FastMCP (Phase 2)

```bash
uv sync --all-groups   # install
uv run pytest -v       # test
uv run ruff check .    # lint
```

## Status

Phase 0 — scaffold. Nothing works yet; this README describes the destination.
