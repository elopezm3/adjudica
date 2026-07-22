"""Extract structured fields from a pliego PDF with Claude.

Claude reads PDFs natively (text-layer and scanned/image-only alike, via vision), so we
send the document bytes straight through — no OCR, no pdf-to-text step. `messages.parse`
with the ExtractedFields schema returns validated structured output.

Only PDFs are handled here. Real corpora also contain .docx and legacy binary .doc served
with wrong content types (see CLAUDE.md constraint 6); those need a convert-to-PDF step
before extraction and are out of scope for this first version — we sniff magic bytes and
refuse non-PDFs loudly rather than feeding Claude something it can't read.
"""

from __future__ import annotations

import base64

from adjudica.config import EXTRACT_MAX_TOKENS, EXTRACT_MODEL
from adjudica.extract.schema import ExtractedFields

_PDF_MAGIC = b"%PDF-"

_PROMPT = """\
Eres un asistente que extrae datos de pliegos de contratación pública española.
Del documento adjunto, extrae únicamente estos campos:

- budget: el presupuesto base de licitación o valor estimado del contrato, como número
  (euros, sin símbolo ni separadores de miles). Si hay varios (con/sin IVA, por lotes),
  usa el importe total del contrato sin IVA. Si no aparece, null.
- cpv_primary: el código CPV principal (8 dígitos). Si hay varios, el primero/principal.
  Si no aparece, null.
- deadline: la fecha límite de presentación de ofertas, en formato YYYY-MM-DD. Si no
  aparece, null.

Extrae solo lo que está escrito en el documento. No inventes ni estimes valores.
Si un campo no está presente, devuelve null para ese campo."""


class ExtractionError(RuntimeError):
    """Extraction did not yield a usable result (refusal, or unparseable output)."""


class UnsupportedDocumentError(ValueError):
    """The document is not a PDF; conversion is required before extraction."""


def _looks_like_pdf(data: bytes) -> bool:
    return data[:5] == _PDF_MAGIC


def extract_from_pdf(
    pdf_bytes: bytes,
    *,
    client,
    model: str = EXTRACT_MODEL,
    max_tokens: int = EXTRACT_MAX_TOKENS,
) -> ExtractedFields:
    """Extract ExtractedFields from a pliego PDF. Raises on non-PDF input or refusal.

    `client` is an anthropic.Anthropic (injected so tests run offline).
    """
    if not _looks_like_pdf(pdf_bytes):
        raise UnsupportedDocumentError("not a PDF (magic bytes mismatch); convert first")

    encoded = base64.standard_b64encode(pdf_bytes).decode("ascii")
    response = client.messages.parse(
        model=model,
        max_tokens=max_tokens,
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
                    {"type": "text", "text": _PROMPT},
                ],
            }
        ],
        output_format=ExtractedFields,
    )

    if getattr(response, "stop_reason", None) == "refusal":
        raise ExtractionError("model refused the extraction request")
    parsed = getattr(response, "parsed_output", None)
    if parsed is None:
        raise ExtractionError("no parsed output returned")
    return parsed
