# Adjudica — Tender Qualification Agent

EU public-procurement tender qualification, built eval-first as an FDE portfolio project.
Read `README.md` for the full picture. Current phase: **0 — eval harness + data spine**.

## Non-negotiable design constraints

These were verified against live endpoints before the project started. Do not rediscover
them the hard way:

1. **Backtest window is bounded on BOTH ends — 2024-H2 to ~2025-H1.** Two forces pull
   opposite ways and the usable window is their intersection (verified live 2026-07,
   see `docs/findings/ted-eforms-boundary.md`):
   - *Award lag 5–18 months* wants OLD tenders so the award already exists.
   - *eForms schema boundary* wants NEW tenders: TED's structured API only projects
     eForms fields, and Spanish notices only carry `procedure-identifier` (and award
     `winner-name`/`tender-value`) from ~2024-H2 onward. 2023 and 2024-H1 notices return
     these fields empty — legacy schema, unusable for structured linkage.
   Net: draw backtest tenders from **2024-H2 onward**, old enough that their awards have
   landed. This widens over time. Do NOT reach back to 2023/early-2024 for linked data.
2. **`clos-nw` ≠ missing award notice.** "Closed without a winner" (*desierto*) is a real
   negative label. "No award notice found" means *not yet published* — unknown, not
   negative. Conflating them corrupts the negative class. Keep three states everywhere:
   `awarded` / `desierto` / `unknown`.
3. **PLACSP: syndication endpoints only.** `robots.txt` on the portal is `Disallow: /`.
   The ATOM feed and open-data channel exist for reuse — use only those. Never crawl
   portal HTML pages. (PLACSP's bulk ZIPs stream too slowly to complete; use ATOM.)
4. **TED is open** (no key, CC BY 4.0) with documented rate limits: 600/IP/6min, 700/min,
   3 concurrent. Respect them; enforcement is untested and we don't want to be the test.
5. **Transient failures are normal.** Retry with backoff on all ingestion HTTP calls.
6. **Documents are hostile.** Expect image-only PDFs (no text layer), `.docx`, legacy
   binary `.doc` served with a `.docx` content type, Spanish and Galician. Sniff real
   file types from magic bytes, never trust extensions or Content-Type headers.

## Eval-first rule

The eval harness is built before the thing it evaluates, in every phase. A capability
without a measured accuracy number and a written failure-mode analysis is not done.
Ground truth must be independent of the system being graded:

- Extraction grades against **eForms XML** fields (published alongside the PDFs).
- Outcome predictions grade against **award notices** (linked by procedure UUID,
  `cbc:ContractFolderID` / BT-04).

## Conventions

| Rule | Description |
|------|-------------|
| uv for everything | `uv sync`, `uv run <cmd>`, `uv add <pkg>`; `uv.lock` is committed |
| ruff lints AND formats | `uv run ruff check .` + `uv run ruff format .` — no black |
| Polars, never Pandas | All dataframe work in Polars; DuckDB for storage/queries |
| Streaming for bulk | `pl.scan_*` over `pl.read_*` for anything large |
| Data is gitignored | `data/` holds downloaded corpora; never commit corpus files |
| Tests must pass | `uv run pytest -v` after changes; fix all failures before done |
| CI is the gate | GitHub Actions runs lint + format check + tests on every push/PR |

## Commits

Conventional commit messages (`feat:`, `fix:`, `chore:`, `docs:`, `test:`).
Never add a Claude/assistant co-author trailer or "Generated with" line.

## Layout

```
src/adjudica/
├── ingest/     # Phase 0: TED + PLACSP ingesters → DuckDB/Parquet
├── evals/      # Phase 0: golden set builder + eval harness
└── extract/    # Phase 1: document → structured requirements (placeholder)
data/           # gitignored corpus storage
docs/           # plans, findings, failure-mode writeups
tests/
```
