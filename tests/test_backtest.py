"""Outcome backtest tests — scoring, baselines, and the imbalance trap. Offline."""

import datetime as dt

import pytest

from adjudica.evals.backtest import (
    BacktestItem,
    Outcome,
    load_resolved_outcomes,
    majority_baseline,
    score_backtest,
)
from adjudica.ingest import resolve, store
from adjudica.ingest.models import NoticeRecord


def _item(i, predicted, actual):
    return BacktestItem(tender_id=f"t{i}", predicted=predicted, actual=actual)


def test_perfect_predictions_score_100():
    items = [
        _item(1, Outcome.AWARDED, Outcome.AWARDED),
        _item(2, Outcome.DESIERTO, Outcome.DESIERTO),
    ]
    report = score_backtest(items)
    assert report.accuracy == 1.0
    assert report.per_class["desierto"].recall == 1.0


def test_majority_baseline_is_reported():
    # 8 awarded, 2 desierto -> always-'awarded' scores 80%.
    actuals = [Outcome.AWARDED] * 8 + [Outcome.DESIERTO] * 2
    label, acc = majority_baseline(actuals)
    assert label == "awarded"
    assert acc == 0.8


def test_lazy_predictor_does_not_beat_baseline():
    """The trap this eval exists to catch: 80% accuracy that is worth nothing."""
    # Predict 'awarded' for everything on an 8/2 split.
    items = [_item(i, Outcome.AWARDED, Outcome.AWARDED) for i in range(8)]
    items += [_item(i + 8, Outcome.AWARDED, Outcome.DESIERTO) for i in range(2)]
    report = score_backtest(items)

    assert report.accuracy == 0.8  # looks respectable...
    assert report.baseline_accuracy == 0.8  # ...but is exactly the baseline
    assert report.lift_over_baseline == 0.0
    assert report.beats_baseline is False
    # And it never once caught the class that matters.
    assert report.per_class["desierto"].recall == 0.0


def test_a_predictor_that_catches_the_minority_class_beats_baseline():
    items = [_item(i, Outcome.AWARDED, Outcome.AWARDED) for i in range(8)]
    items += [_item(i + 8, Outcome.DESIERTO, Outcome.DESIERTO) for i in range(2)]
    report = score_backtest(items)
    assert report.accuracy == 1.0
    assert report.beats_baseline is True
    assert report.lift_over_baseline == pytest.approx(0.2)  # 1.0 - 0.8 is not exactly 0.2


def test_precision_is_none_when_class_never_predicted():
    items = [_item(i, Outcome.AWARDED, Outcome.AWARDED) for i in range(3)]
    report = score_backtest(items)
    assert report.per_class["desierto"].precision is None  # not 0.0 — we never guessed it
    assert report.per_class["desierto"].recall is None  # and there were none to catch


def test_empty_set_is_handled():
    report = score_backtest([])
    assert report.n == 0
    assert "No resolved procedures" in report.format()


def test_report_format_shows_baseline_and_lift():
    items = [_item(i, Outcome.AWARDED, Outcome.AWARDED) for i in range(4)]
    items.append(_item(5, Outcome.DESIERTO, Outcome.DESIERTO))
    out = score_backtest(items).format()
    assert "majority baseline" in out and "lift" in out and "BEATS baseline" in out


def test_load_resolved_outcomes_excludes_unknown():
    """A tender with no award notice yet must not enter the backtest at all."""
    con = store.connect(":memory:")
    store.upsert_notices(
        con,
        [
            # Resolved: awarded.
            NoticeRecord(
                publication_number="T1",
                notice_type="cn-standard",
                kind="tender",
                procedure_id="p1",
                publication_date=dt.date(2024, 9, 1),
            ),
            NoticeRecord(
                publication_number="W1",
                notice_type="can-standard",
                kind="award",
                procedure_id="p1",
                publication_date=dt.date(2025, 3, 1),
                winner_selection_status=["selec-w"],
            ),
            # Resolved: desierto.
            NoticeRecord(
                publication_number="T2",
                notice_type="cn-standard",
                kind="tender",
                procedure_id="p2",
                publication_date=dt.date(2024, 9, 1),
            ),
            NoticeRecord(
                publication_number="W2",
                notice_type="can-standard",
                kind="award",
                procedure_id="p2",
                publication_date=dt.date(2025, 1, 1),
                winner_selection_status=["clos-nw"],
            ),
            # Unresolved: no award notice at all.
            NoticeRecord(
                publication_number="T3",
                notice_type="cn-standard",
                kind="tender",
                procedure_id="p3",
                publication_date=dt.date(2024, 10, 1),
            ),
        ],
    )
    resolve.build_links(con)

    resolved = load_resolved_outcomes(con)
    assert {r["tender_id"] for r in resolved} == {"T1", "T2"}  # T3 excluded
    assert {r["actual"] for r in resolved} == {Outcome.AWARDED, Outcome.DESIERTO}
