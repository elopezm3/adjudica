"""award_outcome classification — the awarded/desierto/None logic (offline)."""

from adjudica.ingest.models import NoticeRecord
from adjudica.ingest.normalize import normalize_notice


def _award(status: list[str], winners: list[str] | None = None) -> NoticeRecord:
    return NoticeRecord(
        publication_number="x",
        notice_type="can-standard",
        kind="award",
        winner_selection_status=status,
        winner_names=winners or [],
    )


def test_selec_w_is_awarded():
    assert _award(["selec-w"]).award_outcome == "awarded"


def test_all_clos_nw_is_desierto():
    assert _award(["clos-nw", "clos-nw"]).award_outcome == "desierto"


def test_mixed_lots_count_as_awarded():
    # One lot found a winner, another didn't -> at least partially awarded.
    assert _award(["selec-w", "clos-nw"]).award_outcome == "awarded"


def test_awarded_even_when_winner_name_missing():
    # The real trap: selec-w with no winner name is still an award, not a desierto.
    assert _award(["selec-w"], winners=[]).award_outcome == "awarded"


def test_absent_status_is_none():
    assert _award([]).award_outcome is None


def test_non_award_is_none():
    rec = NoticeRecord(
        publication_number="x",
        notice_type="cn-standard",
        kind="tender",
        winner_selection_status=["selec-w"],  # ignored: not an award
    )
    assert rec.award_outcome is None


def test_fixture_outcomes(ted_awards):
    outcomes = {
        n["publication-number"]: normalize_notice(n).award_outcome for n in ted_awards["notices"]
    }
    # Fixture was built with 2 desierto + 3 awarded notices.
    assert sorted(outcomes.values()) == ["awarded", "awarded", "awarded", "desierto", "desierto"]
