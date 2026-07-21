# Finding: the TED eForms schema boundary bounds our backtest window

**Date:** 2026-07-17 · **Method:** live probes against `api.ted.europa.eu/v3/notices/search`

## What we verified

The TED v3 search API works as a data source: `POST /v3/notices/search`, HTTP 200, no API
key, cursor pagination via `iterationNextToken`. The response envelope is
`{"notices": [...], "totalNoticeCount": N, "iterationNextToken": ...}`.

Confirmed real field names (the earlier scoping report used raw-XML names, which are wrong
for the API):

| Concept | API field (correct) | Report said (wrong) |
|---|---|---|
| Procedure linkage key | `procedure-identifier` | `cbc:ContractFolderID` (raw XML only; `contract-folder` is not an API field) |
| Winning bidder | `winner-name` (multilingual object; may list multiple) | `winner tax ID` |
| Bid values | `tender-value` (array, per lot/winner) | `PayableAmount` |
| Award total | `result-value-notice` | — |

Multilingual fields (`notice-title`, `buyer-name`, `winner-name`) return an object keyed by
3-letter language code (23 languages). We keep `spa` and `eng` only.

## The boundary

`procedure-identifier` — the key that links a tender notice to its award notice — only
populates for **eForms** notices. Spanish notices crossed into eForms mid-2024:

| Window (Spanish `cn-standard` tenders) | `procedure-identifier` present |
|---|---|
| 2023-H2 | 0/10 sampled |
| 2024-H1 | 0/10 sampled |
| 2024-H2 | 10/10 sampled |

Same effect on award notices: an early-2024 `can-standard` returns `winner-name` /
`tender-value` / `result-value-notice` empty; a 2025 `can-standard` populates all of them.

## Why it matters

The backtest needs a tender linked to its later award, both eForms:

- **Award lag (5–18 mo)** wants the tender OLD so the award exists.
- **eForms boundary** wants the tender NEW so `procedure-identifier` exists.

Intersection = **tenders published 2024-H2 onward**, old enough (by mid-2026) that awards
have landed. The window widens as time passes. Reaching back to 2023 / 2024-H1 for linked
structured data does not work — those notices are legacy schema.

## Consequence for Phase 0

Ingest only eForms notices. The ingester records `procedure-identifier` presence so we can
measure eForms coverage empirically from the data itself rather than trusting these samples.
Legacy-schema notices are out of scope for the linked dataset.
