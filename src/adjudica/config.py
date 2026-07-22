"""Project-wide constants. No secrets — TED needs no API key."""

from __future__ import annotations

TED_SEARCH_URL = "https://api.ted.europa.eu/v3/notices/search"

# PLACSP open-data ATOM syndication (Phase 1 document source). Sanctioned endpoint —
# constraint 3 forbids crawling the portal; this feed exists for reuse. Each entry's CODICE
# XML carries structured fields (ground truth) AND direct pliego links (GetDocumentByIdServlet).
PLACSP_FEED_URL = (
    "https://contrataciondelestado.es/sindicacion/sindicacion_643/"
    "licitacionesPerfilesContratanteCompleto3.atom"
)

# TED documented rate limits: 600/IP/6min, 700/min, 3 concurrent. We observed a 429
# during tight backfill loops, so we also throttle proactively to this interval.
TED_MAX_PAGE_SIZE = 250
TED_DEFAULT_TIMEOUT = 30.0
TED_MIN_REQUEST_INTERVAL_S = 0.5  # ~120 req/min, well under the limit and gentle on bursts

# Preferred languages for multilingual fields, in order. Spanish first, English fallback.
PREFERRED_LANGS = ("spa", "eng")

# Model for document field extraction (Phase 1). Claude reads PDFs natively — scanned or
# text-layer — so no OCR pipeline is needed. This is the tunable knob if cost/latency of a
# full-corpus run argues for a smaller model; default to the most capable.
EXTRACT_MODEL = "claude-opus-4-8"
EXTRACT_MAX_TOKENS = 1024

# USD per 1M tokens, for the --estimate cost projection. From the published price list;
# re-check before quoting figures, since pricing changes. Output cost is negligible here
# (we ask for a handful of structured fields), so only input rates matter in practice.
MODEL_PRICES_USD_PER_MTOK: dict[str, dict[str, float]] = {
    "claude-opus-4-8": {"input": 5.00, "output": 25.00},
    "claude-sonnet-5": {"input": 3.00, "output": 15.00},
    "claude-haiku-4-5": {"input": 1.00, "output": 5.00},
}

# The eForms fields we ingest. All verified to populate on 2024-H2+ Spanish notices.
# See docs/findings/ted-eforms-boundary.md for why only eForms notices are in scope.
TED_FIELDS = (
    "publication-number",
    "notice-type",
    "procedure-identifier",
    "classification-cpv",
    "buyer-name",
    "notice-title",
    "publication-date",
    "deadline-receipt-tender-date-lot",
    "estimated-value-lot",
    "winner-name",
    # eForms BT-142 "Winner Chosen", per lot: selec-w (awarded) / clos-nw (desierto).
    # The authoritative outcome signal — winner-name presence is NOT reliable.
    "winner-selection-status",
    "tender-value",
    "result-value-notice",
)
