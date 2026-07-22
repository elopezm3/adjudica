"""Eligibility rule tests — pure logic, offline.

The scenario mirrors the worked example: LimpiaSur, a Seville cleaning company.
"""

import pytest

from adjudica.extract.schema import ExtractedFields
from adjudica.qualify.eligibility import RuleOutcome, Verdict, check_eligibility
from adjudica.qualify.profile import CompanyProfile

LIMPIASUR = CompanyProfile(
    name="LimpiaSur S.L.",
    cpv_prefixes=["9091", "5531"],  # building cleaning, canteen services
    annual_turnover=900_000,
    certifications=["ISO 9001", "ISO 14001"],
)


def _tender(**kw) -> ExtractedFields:
    base = dict(budget=331_252.82, cpv_primary="90911200")
    return ExtractedFields(**{**base, **kw})


def test_eligible_when_every_checkable_rule_passes():
    fields = _tender(solvency_turnover_required=250_000, required_certifications=["ISO 9001"])
    result = check_eligibility(LIMPIASUR, fields)
    assert result.verdict is Verdict.ELIGIBLE
    assert result.blocking_reasons == []


def test_turnover_below_floor_disqualifies():
    # The Madrid-metro case: €6M turnover required, LimpiaSur has €900k.
    fields = _tender(
        budget=12_000_000, solvency_turnover_required=6_000_000, required_certifications=[]
    )
    result = check_eligibility(LIMPIASUR, fields)
    assert result.verdict is Verdict.NOT_ELIGIBLE
    assert any("below the floor" in r for r in result.blocking_reasons)


def test_out_of_scope_cpv_disqualifies():
    # IT services tender — not this company's line of work.
    fields = _tender(cpv_primary="72000000", solvency_turnover_required=100_000)
    result = check_eligibility(LIMPIASUR, fields)
    assert result.verdict is Verdict.NOT_ELIGIBLE
    assert any("outside" in r for r in result.blocking_reasons)


def test_missing_certification_disqualifies():
    fields = _tender(
        solvency_turnover_required=250_000,
        required_certifications=["ISO 9001", "ISO 45001"],  # 45001 not held
    )
    result = check_eligibility(LIMPIASUR, fields)
    assert result.verdict is Verdict.NOT_ELIGIBLE
    assert any("ISO 45001" in r for r in result.blocking_reasons)


def test_certification_match_is_case_insensitive():
    fields = _tender(solvency_turnover_required=250_000, required_certifications=["iso 9001  "])
    assert check_eligibility(LIMPIASUR, fields).verdict is Verdict.ELIGIBLE


def test_unknown_when_a_rule_cannot_be_checked():
    # No turnover requirement extracted -> we cannot confirm solvency -> UNKNOWN, not ELIGIBLE.
    fields = _tender(solvency_turnover_required=None, required_certifications=["ISO 9001"])
    result = check_eligibility(LIMPIASUR, fields)
    assert result.verdict is Verdict.UNKNOWN
    assert result.blocking_reasons == []
    assert any("no turnover requirement" in u for u in result.unverified)


def test_unknown_never_upgrades_to_eligible():
    # Everything unknown: no CPV, no thresholds. Must NOT claim eligible.
    result = check_eligibility(LIMPIASUR, ExtractedFields())
    assert result.verdict is Verdict.UNKNOWN


def test_failure_beats_unknown():
    # One hard failure plus one gap -> NOT_ELIGIBLE wins (don't bid).
    fields = _tender(cpv_primary="72000000", solvency_turnover_required=None)
    assert check_eligibility(LIMPIASUR, fields).verdict is Verdict.NOT_ELIGIBLE


def test_capacity_ceiling_is_opt_in():
    cautious = LIMPIASUR.model_copy(update={"max_contract_value": 500_000})
    fields = _tender(budget=800_000, solvency_turnover_required=250_000)
    result = check_eligibility(cautious, fields)
    assert result.verdict is Verdict.NOT_ELIGIBLE
    assert any("exceeds capacity" in r for r in result.blocking_reasons)


def test_not_applicable_does_not_count_as_unverified():
    """A rule the company opted out of must not look like missing tender data."""
    fields = _tender(solvency_turnover_required=250_000, required_certifications=["ISO 9001"])
    result = check_eligibility(LIMPIASUR, fields)  # no max_contract_value set
    capacity = next(c for c in result.checks if c.rule == "capacity")
    assert capacity.outcome is RuleOutcome.NOT_APPLICABLE
    assert capacity.detail not in result.unverified  # excluded from "confirm by hand"
    assert result.verdict is Verdict.ELIGIBLE  # and it does not block eligibility


def test_every_check_is_reported_even_when_eligible():
    """The verdict is auditable: all four rules always appear with their outcome."""
    fields = _tender(solvency_turnover_required=250_000, required_certifications=["ISO 9001"])
    result = check_eligibility(LIMPIASUR, fields)
    assert {c.rule for c in result.checks} == {"scope", "solvency", "certifications", "capacity"}


@pytest.mark.parametrize(
    ("cpv", "served"),
    [("90911200", True), ("55311000", True), ("45212200", False), (None, False)],
)
def test_cpv_prefix_matching(cpv, served):
    assert LIMPIASUR.serves_cpv(cpv) is served
