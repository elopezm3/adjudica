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

| Phase | Deliverable | Ground truth | State |
|-------|-------------|--------------|-------|
| 0 | Data spine: TED + PLACSP → DuckDB, tender→award resolver | — | ✅ |
| 1 | Extraction from pliego PDFs + extraction eval harness | CODICE/eForms XML | ✅ built · live run needs an API key |
| 2 | MCP server + qualification (profile, eligibility rules) | Stated tender rules | ✅ |
| 3 | Outcome backtest harness (vs. majority baseline) | Award notices | ✅ harness · predictor needs an API key |
| 4 | Engagement write-up | — | ✅ [`docs/CASE_STUDY.md`](docs/CASE_STUDY.md) |

In every phase the eval harness is built **before** the thing it measures. That ordering is
the project's thesis, and [the write-up](docs/CASE_STUDY.md) explains what it caught.

## Using it

The MCP server is the product surface — connect it to Claude Desktop and ask in plain
language. It needs no Anthropic API key; Claude is the client.

```bash
uv sync --all-groups
uv run python -m adjudica.placsp.ingest --max 400     # load live Spanish tenders
```

```jsonc
// claude_desktop_config.json
{"mcpServers": {"adjudica": {
  "command": "uv",
  "args": ["run", "--directory", "/path/to/adjudica", "python", "-m", "adjudica.mcp_server.server"]
}}}
```

Tools: `search_tenders`, `get_tender`, `check_tender_eligibility`, `past_awards_for_cpv`.

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

All four phases are built. 93 offline tests, CI green. Verified against live sources:
TED's API contract, the PLACSP feed and CODICE schema, and a real 3.7 MB pliego download.

The one thing outstanding is running the two predictors (extraction and outcome judgment)
against real data, which needs Anthropic API billing. The harnesses that will grade them
are done — deliberately, since building the ruler first is the point.
