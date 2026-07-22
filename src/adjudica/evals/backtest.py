"""Outcome backtest — grade predicted tender outcomes against what actually happened.

The task: given a tender, predict whether it will be AWARDED or go DESIERTO (closed with
no winner). Ground truth comes from the award notice, published months later, so this is a
real prediction graded against an independent published record.

Two things make this eval honest rather than flattering:

1. UNKNOWN is excluded, never treated as a negative. A tender with no award notice yet has
   no ground truth — scoring it would invent an answer. Only resolved procedures count.

2. Every report carries a MAJORITY BASELINE. Outcomes are heavily imbalanced (most tenders
   are awarded), so a predictor that blindly says "awarded" every time can score ~90%
   accuracy while being useless. A model is only interesting if it beats that floor, so the
   floor is reported next to the score and lift is computed against it — never accuracy alone.
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from enum import StrEnum
from typing import Any

import duckdb


class Outcome(StrEnum):
    AWARDED = "awarded"
    DESIERTO = "desierto"


@dataclass(frozen=True)
class BacktestItem:
    """One graded prediction."""

    tender_id: str
    predicted: Outcome
    actual: Outcome

    @property
    def correct(self) -> bool:
        return self.predicted is self.actual


@dataclass
class ClassMetrics:
    """Precision/recall for one outcome class."""

    label: str
    support: int  # how many items truly belong to this class
    predicted: int  # how many we predicted as this class
    true_positives: int

    @property
    def precision(self) -> float | None:
        """Of the ones we called X, how many were X? None if we never predicted X."""
        return self.true_positives / self.predicted if self.predicted else None

    @property
    def recall(self) -> float | None:
        """Of the real Xs, how many did we catch? None if there are none in the set."""
        return self.true_positives / self.support if self.support else None

    @property
    def f1(self) -> float | None:
        p, r = self.precision, self.recall
        if p is None or r is None or (p + r) == 0:
            return None
        return 2 * p * r / (p + r)


@dataclass
class BacktestReport:
    n: int
    accuracy: float | None
    per_class: dict[str, ClassMetrics]
    baseline_label: str | None
    baseline_accuracy: float | None

    @property
    def lift_over_baseline(self) -> float | None:
        """Accuracy points gained over always guessing the majority class."""
        if self.accuracy is None or self.baseline_accuracy is None:
            return None
        return self.accuracy - self.baseline_accuracy

    @property
    def beats_baseline(self) -> bool:
        lift = self.lift_over_baseline
        return lift is not None and lift > 0

    def format(self) -> str:
        if not self.n:
            return "No resolved procedures to grade (all outcomes unknown)."
        lines = [
            f"Backtest over {self.n} resolved procedures",
            f"  accuracy            {self.accuracy:.1%}",
            f"  majority baseline   {self.baseline_accuracy:.1%}  "
            f"(always predict '{self.baseline_label}')",
        ]
        lift = self.lift_over_baseline
        verdict = "BEATS baseline" if self.beats_baseline else "does NOT beat baseline"
        lines.append(f"  lift                {lift:+.1%}  -> {verdict}")
        lines.append("")
        lines.append("  class       support  precision  recall     f1")
        for label, m in self.per_class.items():

            def _fmt(v: float | None) -> str:
                return "   --  " if v is None else f"{v:>6.1%}"

            lines.append(
                f"  {label:<10} {m.support:>7}  {_fmt(m.precision)}  {_fmt(m.recall)}  {_fmt(m.f1)}"
            )
        return "\n".join(lines)


def majority_baseline(actuals: Sequence[Outcome]) -> tuple[str | None, float | None]:
    """The label to beat and the accuracy of always predicting it."""
    if not actuals:
        return None, None
    label, count = Counter(actuals).most_common(1)[0]
    return str(label), count / len(actuals)


def score_backtest(items: Iterable[BacktestItem]) -> BacktestReport:
    """Aggregate graded predictions into a report, always against the majority baseline."""
    items = list(items)
    if not items:
        return BacktestReport(0, None, {}, None, None)

    actuals = [i.actual for i in items]
    accuracy = sum(i.correct for i in items) / len(items)
    baseline_label, baseline_accuracy = majority_baseline(actuals)

    per_class: dict[str, ClassMetrics] = {}
    for outcome in Outcome:
        per_class[str(outcome)] = ClassMetrics(
            label=str(outcome),
            support=sum(1 for i in items if i.actual is outcome),
            predicted=sum(1 for i in items if i.predicted is outcome),
            true_positives=sum(1 for i in items if i.predicted is outcome and i.correct),
        )

    return BacktestReport(
        n=len(items),
        accuracy=accuracy,
        per_class=per_class,
        baseline_label=baseline_label,
        baseline_accuracy=baseline_accuracy,
    )


def load_resolved_outcomes(con: duckdb.DuckDBPyConnection) -> list[dict[str, Any]]:
    """Tenders whose outcome is actually known, from the Phase-0 procedure_links table.

    Rows with outcome 'unknown' (no award notice yet) are excluded — they have no ground
    truth, and counting them as 'not desierto' would fabricate answers.
    """
    rows = con.execute(
        """
        SELECT procedure_id, tender_pub, tender_date, outcome, result_value, lag_days
        FROM procedure_links
        WHERE outcome IN ('awarded', 'desierto')
        ORDER BY tender_date
        """
    ).fetchall()
    return [
        {
            "procedure_id": pid,
            "tender_id": tender_pub,
            "tender_date": tender_date,
            "actual": Outcome(outcome),
            "result_value": result_value,
            "lag_days": lag_days,
        }
        for pid, tender_pub, tender_date, outcome, result_value, lag_days in rows
    ]
