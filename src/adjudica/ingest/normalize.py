"""Pure functions that flatten a raw TED search hit into a NoticeRecord.

Everything here is offline and deterministic — the network lives in ted_client.py.
Shapes handled (verified against live 2024-H2+ Spanish notices):
- multilingual objects: {"spa": ["..."], "eng": ["..."], ...} or {"spa": "..."}
- arrays with duplicates: classification-cpv, tender-value, estimated-value-lot
- dates as "YYYY-MM-DD+HH:MM" (date + TZ offset, no time component we need)
"""

from __future__ import annotations

import datetime as dt
from typing import Any

from adjudica.config import PREFERRED_LANGS
from adjudica.ingest.models import NoticeKind, NoticeRecord


def pick_lang(value: Any, langs: tuple[str, ...] = PREFERRED_LANGS) -> str | None:
    """Collapse a multilingual object to one string, preferring `langs` in order.

    Each language maps to either a string or a list of strings; we take the first.
    Falls back to any available language so we never silently drop content.
    """
    if value is None:
        return None
    if isinstance(value, str):
        return value or None
    if isinstance(value, dict):
        for lang in (*langs, *value.keys()):
            got = value.get(lang)
            if isinstance(got, list):
                got = got[0] if got else None
            if isinstance(got, str) and got:
                return got
    return None


def dedup_keep_order(items: list[str]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for it in items:
        if it not in seen:
            seen.add(it)
            out.append(it)
    return out


def as_str_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, list):
        return [str(v) for v in value if v is not None]
    return [str(value)]


def as_float_list(value: Any) -> list[float]:
    out: list[float] = []
    for v in as_str_list(value):
        try:
            out.append(float(v))
        except ValueError:
            continue
    return out


def first_float(value: Any) -> float | None:
    vals = as_float_list(value)
    return vals[0] if vals else None


def parse_ted_date(value: Any) -> dt.date | None:
    """Parse the leading YYYY-MM-DD of a TED date like '2025-01-02+01:00'."""
    if isinstance(value, list):
        value = value[0] if value else None
    if not isinstance(value, str) or len(value) < 10:
        return None
    try:
        return dt.date.fromisoformat(value[:10])
    except ValueError:
        return None


def classify(notice_type: str) -> NoticeKind:
    """Map a TED notice-type to our coarse kind. cn* = tender, can* = award."""
    if notice_type.startswith("can"):
        return "award"
    if notice_type.startswith("cn"):
        return "tender"
    return "other"


def normalize_notice(raw: dict[str, Any]) -> NoticeRecord:
    """Flatten one raw TED search hit into a NoticeRecord."""
    notice_type = str(raw.get("notice-type", ""))
    cpv = dedup_keep_order(as_str_list(raw.get("classification-cpv")))

    return NoticeRecord(
        publication_number=str(raw["publication-number"]),
        notice_type=notice_type,
        kind=classify(notice_type),
        procedure_id=raw.get("procedure-identifier"),
        cpv=cpv,
        cpv_primary=cpv[0] if cpv else None,
        buyer_name=pick_lang(raw.get("buyer-name")),
        title=pick_lang(raw.get("notice-title")),
        publication_date=parse_ted_date(raw.get("publication-date")),
        deadline=parse_ted_date(raw.get("deadline-receipt-tender-date-lot")),
        estimated_value=first_float(raw.get("estimated-value-lot")),
        winner_names=dedup_keep_order(_pick_lang_list(raw.get("winner-name"))),
        winner_selection_status=as_str_list(raw.get("winner-selection-status")),
        tender_values=as_float_list(raw.get("tender-value")),
        result_value=first_float(raw.get("result-value-notice")),
    )


def _pick_lang_list(value: Any, langs: tuple[str, ...] = PREFERRED_LANGS) -> list[str]:
    """Like pick_lang, but keeps ALL names for the chosen language (multiple winners)."""
    if value is None:
        return []
    if isinstance(value, str):
        return [value] if value else []
    if isinstance(value, dict):
        for lang in (*langs, *value.keys()):
            got = value.get(lang)
            if isinstance(got, list) and got:
                return [str(g) for g in got if g]
            if isinstance(got, str) and got:
                return [got]
    return []
