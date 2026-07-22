"""Project the cost of an extraction run before spending anything.

Anthropic's token-counting endpoint is free, so we can measure the exact input size of
real documents and price the run precisely — rather than guessing from page counts and
being surprised by the bill.
"""

from __future__ import annotations

import base64
from dataclasses import dataclass

from adjudica.config import EXTRACT_MODEL, MODEL_PRICES_USD_PER_MTOK


@dataclass
class CostEstimate:
    model: str
    documents: int
    input_tokens: int
    usd: float

    @property
    def usd_per_document(self) -> float:
        return self.usd / self.documents if self.documents else 0.0

    def format(self) -> str:
        return (
            f"Estimated cost for {self.documents} document(s) on {self.model}:\n"
            f"  input tokens   {self.input_tokens:,}\n"
            f"  cost           ${self.usd:.2f}  "
            f"(${self.usd_per_document:.3f} per document)"
        )


def count_document_tokens(pdf_bytes: bytes, *, client, model: str = EXTRACT_MODEL) -> int:
    """Exact input-token count for one PDF, via the free count_tokens endpoint."""
    encoded = base64.standard_b64encode(pdf_bytes).decode("ascii")
    resp = client.messages.count_tokens(
        model=model,
        messages=[
            {
                "role": "user",
                "content": [
                    {
                        "type": "document",
                        "source": {
                            "type": "base64",
                            "media_type": "application/pdf",
                            "data": encoded,
                        },
                    },
                    {"type": "text", "text": "extract fields"},
                ],
            }
        ],
    )
    return resp.input_tokens


def estimate_cost(documents: list[bytes], *, client, model: str = EXTRACT_MODEL) -> CostEstimate:
    """Price a run over real documents. Unknown models fall back to Opus rates (the
    most expensive), so an estimate is never accidentally optimistic."""
    total_tokens = sum(count_document_tokens(d, client=client, model=model) for d in documents)
    rate = MODEL_PRICES_USD_PER_MTOK.get(model, MODEL_PRICES_USD_PER_MTOK["claude-opus-4-8"])
    usd = total_tokens / 1_000_000 * rate["input"]
    return CostEstimate(model=model, documents=len(documents), input_tokens=total_tokens, usd=usd)
