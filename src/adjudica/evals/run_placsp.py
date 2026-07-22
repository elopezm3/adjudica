"""Phase-1 end-to-end on real PLACSP data: feed -> download pliego -> extract -> score.

For each feed entry that has a legal pliego (PCAP) and gradable ground truth, download the
PDF, extract fields with Claude, and grade against the entry's CODICE XML. Produces the
first real extraction Scorecard. A download failure or unreadable document is graded as an
empty extraction (a miss on every field), never dropped — the accuracy stays honest.
"""

from __future__ import annotations

import httpx

from adjudica.evals.extraction import Scorecard, score
from adjudica.evals.run_extraction import evaluate_documents
from adjudica.ingest.models import NoticeRecord
from adjudica.placsp.documents import DocumentDownloadError, download_document
from adjudica.placsp.feed import iter_feed
from adjudica.placsp.parse import to_notice


def _has_ground_truth(rec: NoticeRecord) -> bool:
    return any(v is not None for v in (rec.estimated_value, rec.cpv_primary, rec.deadline))


def evaluate_placsp(
    *,
    http_client: httpx.Client,
    anthropic_client,
    max_docs: int = 25,
) -> Scorecard:
    """Grade extraction over up to max_docs real PLACSP tenders that have a PCAP."""
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

    if not items:
        return score([])
    return evaluate_documents(items, client=anthropic_client)


def main() -> None:
    """Run the real Phase-1 extraction eval. Needs ANTHROPIC_API_KEY (or an `ant` profile).

    Usage: uv run python -m adjudica.evals.run_placsp [--max N]
    """
    import argparse

    import anthropic

    from adjudica.placsp.documents import new_client

    parser = argparse.ArgumentParser(description="Phase-1 extraction eval over live PLACSP data.")
    parser.add_argument("--max", dest="max_docs", type=int, default=25)
    args = parser.parse_args()

    http_client = new_client()
    try:
        card = evaluate_placsp(
            http_client=http_client,
            anthropic_client=anthropic.Anthropic(),
            max_docs=args.max_docs,
        )
    finally:
        http_client.close()

    print(f"Extraction eval over {args.max_docs} PLACSP tenders:\n")
    print(card.format())


if __name__ == "__main__":
    main()
