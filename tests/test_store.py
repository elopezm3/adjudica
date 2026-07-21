"""DuckDB store tests — in-memory, offline."""

from adjudica.ingest import store
from adjudica.ingest.normalize import normalize_notice


def _records(env):
    return [normalize_notice(r) for r in env["notices"]]


def test_roundtrip_preserves_lists_and_scalars(ted_awards):
    con = store.connect(":memory:")
    recs = _records(ted_awards)
    written = store.upsert_notices(con, recs)
    assert written == len(recs)

    row = con.execute(
        "SELECT winner_names, cpv, result_value FROM notices WHERE publication_number = ?",
        [recs[0].publication_number],
    ).fetchone()
    winner_names, cpv, result_value = row
    assert winner_names == recs[0].winner_names  # DuckDB LIST round-trips to a Python list
    assert cpv == recs[0].cpv
    assert result_value == recs[0].result_value


def test_upsert_is_idempotent(ted_tenders):
    con = store.connect(":memory:")
    recs = _records(ted_tenders)
    store.upsert_notices(con, recs)
    store.upsert_notices(con, recs)  # same rows again
    count = con.execute("SELECT count(*) FROM notices").fetchone()[0]
    assert count == len(recs)  # replaced, not duplicated


def test_eforms_coverage(ted_tenders, ted_awards):
    con = store.connect(":memory:")
    store.upsert_notices(con, _records(ted_tenders) + _records(ted_awards))
    cov = store.eforms_coverage(con)
    assert cov["total"] == len(ted_tenders["notices"]) + len(ted_awards["notices"])
    assert cov["eforms_fraction"] == 1.0  # all fixtures are eForms


def test_empty_upsert_is_noop():
    con = store.connect(":memory:")
    assert store.upsert_notices(con, []) == 0
