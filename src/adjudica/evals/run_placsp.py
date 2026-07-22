"""Phase-1 end-to-end on real PLACSP data: feed -> download pliego -> extract -> score.

For each feed entry that has a legal pliego (PCAP) and gradable ground truth, download the
PDF, extract fields with Claude, and grade against the entry's CODICE XML. Produces the
first real extraction Scorecard. A download failure or unreadable document is graded as an
empty extraction (a miss on every field), never dropped — the accuracy stays honest.
"""

from __future__ import annotations

import httpx

from adjudica.config import EXTRACT_MODEL
from adjudica.evals.extraction import Scorecard, score
from adjudica.evals.run_extraction import evaluate_documents
from adjudica.ingest.models import NoticeRecord
from adjudica.placsp.documents import DocumentDownloadError, download_document
from adjudica.placsp.feed import iter_feed
from adjudica.placsp.parse import to_notice


def _has_ground_truth(rec: NoticeRecord) -> bool:
    return any(v is not None for v in (rec.estimated_value, rec.cpv_primary, rec.deadline))


def collect_documents(
    http_client: httpx.Client, *, max_docs: int
) -> list[tuple[bytes, NoticeRecord]]:
    """Download up to max_docs real pliegos with their ground truth. No API cost."""
    items: list[tuple[bytes, NoticeRecord]] = []
    for entry in iter_feed(http_client):
        legal = entry.legal_documents
        truth = to_notice(entry)
        if not legal or not _has_ground_truth(truth):
            continue
        try:
            pdf = download_document(legal[0].uri, client=http_client)
        except DocumentDownloadError:
            pdf = b""  # download failed -> empty -> counts as all-missed
        items.append((pdf, truth))
        if len(items) >= max_docs:
            break
    return items


def evaluate_placsp(
    *,
    http_client: httpx.Client,
    anthropic_client,
    max_docs: int = 25,
    model: str = EXTRACT_MODEL,
) -> Scorecard:
    """Grade extraction over up to max_docs real PLACSP tenders that have a PCAP."""
    items = collect_documents(http_client, max_docs=max_docs)
    if not items:
        return score([])
    return evaluate_documents(items, client=anthropic_client, model=model)


def main() -> None:
    """Run the real Phase-1 extraction eval. Needs ANTHROPIC_API_KEY (or an `ant` profile).

    Check the price first (free — uses token counting, makes no model calls):
        uv run python -m adjudica.evals.run_placsp --max 5 --estimate

    Then run it:
        uv run python -m adjudica.evals.run_placsp --max 5 --model claude-haiku-4-5
    """
    import argparse

    import anthropic

    from adjudica.evals.cost import estimate_cost
    from adjudica.placsp.documents import new_client

    parser = argparse.ArgumentParser(description="Phase-1 extraction eval over live PLACSP data.")
    parser.add_argument("--max", dest="max_docs", type=int, default=25)
    parser.add_argument(
        "--model",
        default=EXTRACT_MODEL,
        help=f"extraction model (default {EXTRACT_MODEL}; claude-haiku-4-5 is ~5x cheaper)",
    )
    parser.add_argument(
        "--estimate",
        action="store_true",
        help="print the projected cost and exit without running any extraction",
    )
    args = parser.parse_args()

    http_client = new_client()
    try:
        items = collect_documents(http_client, max_docs=args.max_docs)
        if not items:
            print("No gradable tenders with pliegos found in the feed.")
            return

        client = anthropic.Anthropic()
        pdfs = [pdf for pdf, _ in items]

        # Always price the run first so the cost is never a surprise.
        estimate = estimate_cost(pdfs, client=client, model=args.model)
        print(estimate.format())
        if args.estimate:
            print("\n--estimate given: stopping before any extraction. No model calls made.")
            return

        print(f"\nExtracting {len(items)} document(s)...\n")
        card = evaluate_documents(items, client=client, model=args.model)
    finally:
        http_client.close()

    print(card.format())


if __name__ == "__main__":
    main()
