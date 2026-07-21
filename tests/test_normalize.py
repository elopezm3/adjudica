"""Normalization tests against real TED fixtures — fully offline."""

import datetime as dt

from adjudica.ingest.normalize import (
    classify,
    dedup_keep_order,
    normalize_notice,
    parse_ted_date,
    pick_lang,
)


def test_pick_lang_prefers_spanish():
    assert pick_lang({"eng": "English", "spa": "Español"}) == "Español"


def test_pick_lang_handles_list_values():
    assert pick_lang({"spa": ["first", "second"]}) == "first"


def test_pick_lang_falls_back_to_any_language():
    assert pick_lang({"fra": "Bonjour"}) == "Bonjour"


def test_pick_lang_none_and_empty():
    assert pick_lang(None) is None
    assert pick_lang({}) is None
    assert pick_lang({"spa": []}) is None


def test_parse_ted_date_strips_tz_offset():
    assert parse_ted_date("2025-01-02+01:00") == dt.date(2025, 1, 2)
    assert parse_ted_date(["2024-10-15+02:00"]) == dt.date(2024, 10, 15)
    assert parse_ted_date(None) is None
    assert parse_ted_date("garbage") is None


def test_dedup_keeps_first_order():
    assert dedup_keep_order(["a", "b", "a", "c", "b"]) == ["a", "b", "c"]


def test_classify():
    assert classify("cn-standard") == "tender"
    assert classify("can-standard") == "award"
    assert classify("corr") == "other"


def test_normalize_real_tender(ted_tenders):
    rec = normalize_notice(ted_tenders["notices"][0])
    assert rec.kind == "tender"
    assert rec.is_eforms is True  # 2024-H2 eForms notice carries a procedure id
    assert rec.procedure_id
    assert rec.cpv and rec.cpv_primary == rec.cpv[0]
    assert rec.title and rec.buyer_name
    assert rec.publication_date and rec.publication_date.year == 2024
    # Tenders have no award outcome.
    assert rec.winner_names == []
    assert rec.result_value is None


def test_normalize_real_award(ted_awards):
    # Find an awarded (not desierto) notice in the fixture.
    awarded = next(
        normalize_notice(n)
        for n in ted_awards["notices"]
        if normalize_notice(n).award_outcome == "awarded"
    )
    assert awarded.kind == "award"
    assert awarded.is_eforms is True
    assert awarded.winner_names, "an awarded notice should list a winner"
    assert awarded.winner_selection_status  # the authoritative outcome field is captured
    assert all(isinstance(v, float) for v in awarded.tender_values)


def test_normalize_cpv_deduplicates(ted_awards):
    # The award fixture has duplicated CPVs across lots; normalization collapses them.
    rec = normalize_notice(ted_awards["notices"][0])
    assert len(rec.cpv) == len(set(rec.cpv))


def test_every_fixture_notice_normalizes(ted_tenders, ted_awards):
    for env in (ted_tenders, ted_awards):
        for raw in env["notices"]:
            rec = normalize_notice(raw)
            assert rec.publication_number
