"""Hard eligibility rules — can this company legally bid on this tender?

Each rule reports one of four outcomes, and the distinction between the last two matters:

    PASS            the rule was checked and satisfied
    FAIL            the rule was checked and violated — legally disqualified
    UNVERIFIED      the TENDER didn't give us what we need (missing threshold, or
                    extraction missed it). We cannot claim eligibility.
    NOT_APPLICABLE  the rule doesn't apply here — e.g. the COMPANY set no contract
                    ceiling. Nothing to check, so it must not drag the verdict down.

Verdict: any FAIL ⇒ NOT_ELIGIBLE; else any UNVERIFIED ⇒ UNKNOWN; else ELIGIBLE.

UNKNOWN is never collapsed into ELIGIBLE. Telling a customer they qualify when we
couldn't verify it is the expensive kind of wrong: they'd spend days on a bid that gets
thrown out. Every verdict carries per-rule detail so the reasoning is auditable.
"""

from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel

from adjudica.extract.schema import ExtractedFields
from adjudica.qualify.profile import CompanyProfile


class Verdict(StrEnum):
    ELIGIBLE = "eligible"
    NOT_ELIGIBLE = "not_eligible"
    UNKNOWN = "unknown"


class RuleOutcome(StrEnum):
    PASS = "pass"
    FAIL = "fail"
    UNVERIFIED = "unverified"
    NOT_APPLICABLE = "not_applicable"


class RuleCheck(BaseModel):
    rule: str
    outcome: RuleOutcome
    detail: str


class EligibilityResult(BaseModel):
    verdict: Verdict
    checks: list[RuleCheck]

    @property
    def blocking_reasons(self) -> list[str]:
        """Why the company is disqualified — empty unless the verdict is NOT_ELIGIBLE."""
        return [c.detail for c in self.checks if c.outcome is RuleOutcome.FAIL]

    @property
    def unverified(self) -> list[str]:
        """Rules the tender data couldn't settle — what to confirm by hand before bidding."""
        return [c.detail for c in self.checks if c.outcome is RuleOutcome.UNVERIFIED]


def _pass_fail(ok: bool) -> RuleOutcome:
    return RuleOutcome.PASS if ok else RuleOutcome.FAIL


def _check_scope(profile: CompanyProfile, fields: ExtractedFields) -> RuleCheck:
    if not profile.cpv_prefixes:
        return RuleCheck(
            rule="scope",
            outcome=RuleOutcome.NOT_APPLICABLE,
            detail="company declares no CPV families",
        )
    if not fields.cpv_primary:
        return RuleCheck(rule="scope", outcome=RuleOutcome.UNVERIFIED, detail="tender CPV unknown")
    ok = profile.serves_cpv(fields.cpv_primary)
    return RuleCheck(
        rule="scope",
        outcome=_pass_fail(ok),
        detail=(
            f"CPV {fields.cpv_primary} {'matches' if ok else 'is outside'} the company's "
            f"families ({', '.join(profile.cpv_prefixes)})"
        ),
    )


def _check_solvency(profile: CompanyProfile, fields: ExtractedFields) -> RuleCheck:
    if profile.annual_turnover is None:
        return RuleCheck(
            rule="solvency",
            outcome=RuleOutcome.NOT_APPLICABLE,
            detail="company turnover not declared",
        )
    required = fields.solvency_turnover_required
    if required is None:
        return RuleCheck(
            rule="solvency",
            outcome=RuleOutcome.UNVERIFIED,
            detail="no turnover requirement found in the pliego",
        )
    ok = profile.annual_turnover >= required
    return RuleCheck(
        rule="solvency",
        outcome=_pass_fail(ok),
        detail=(
            f"turnover {profile.annual_turnover:,.0f} EUR vs required {required:,.0f} EUR"
            f" — {'meets' if ok else 'below'} the floor"
        ),
    )


def _check_certifications(profile: CompanyProfile, fields: ExtractedFields) -> RuleCheck:
    required = fields.required_certifications
    if not required:
        # Ambiguous by nature: either none are demanded, or extraction missed the clause.
        return RuleCheck(
            rule="certifications",
            outcome=RuleOutcome.UNVERIFIED,
            detail="no certification requirement found in the pliego",
        )
    missing = [c for c in required if not profile.has_certification(c)]
    return RuleCheck(
        rule="certifications",
        outcome=_pass_fail(not missing),
        detail=(
            f"missing: {', '.join(missing)}"
            if missing
            else f"holds all required ({', '.join(required)})"
        ),
    )


def _check_capacity(profile: CompanyProfile, fields: ExtractedFields) -> RuleCheck:
    cap = profile.max_contract_value
    if cap is None:
        return RuleCheck(
            rule="capacity",
            outcome=RuleOutcome.NOT_APPLICABLE,
            detail="no self-imposed contract ceiling",
        )
    if fields.budget is None:
        return RuleCheck(
            rule="capacity", outcome=RuleOutcome.UNVERIFIED, detail="tender budget unknown"
        )
    ok = fields.budget <= cap
    return RuleCheck(
        rule="capacity",
        outcome=_pass_fail(ok),
        detail=(
            f"budget {fields.budget:,.0f} EUR vs ceiling {cap:,.0f} EUR"
            f" — {'within' if ok else 'exceeds'} capacity"
        ),
    )


def check_eligibility(profile: CompanyProfile, fields: ExtractedFields) -> EligibilityResult:
    """Run every hard rule. Any FAIL ⇒ NOT_ELIGIBLE; any UNVERIFIED ⇒ UNKNOWN."""
    checks = [
        _check_scope(profile, fields),
        _check_solvency(profile, fields),
        _check_certifications(profile, fields),
        _check_capacity(profile, fields),
    ]
    if any(c.outcome is RuleOutcome.FAIL for c in checks):
        verdict = Verdict.NOT_ELIGIBLE
    elif any(c.outcome is RuleOutcome.UNVERIFIED for c in checks):
        verdict = Verdict.UNKNOWN
    else:
        verdict = Verdict.ELIGIBLE
    return EligibilityResult(verdict=verdict, checks=checks)
