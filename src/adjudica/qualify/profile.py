"""The bidding company's capabilities — what we check tenders against."""

from __future__ import annotations

from pydantic import BaseModel, Field


class CompanyProfile(BaseModel):
    """What a bidder can do. Supplied once by the customer; checked against every tender."""

    name: str
    # CPV families the company serves, as code prefixes. "9091" matches CPV 90911200
    # (building-cleaning); a full 8-digit code matches only itself.
    cpv_prefixes: list[str] = Field(default_factory=list)
    # Annual turnover ("facturación") in euros — compared against a tender's solvency floor.
    annual_turnover: float | None = None
    certifications: list[str] = Field(default_factory=list)
    # Largest contract the company can realistically deliver, if they want that ceiling
    # enforced. None means no self-imposed cap.
    max_contract_value: float | None = None

    def serves_cpv(self, cpv: str | None) -> bool:
        """True if the CPV falls in one of the company's families."""
        if not cpv or not self.cpv_prefixes:
            return False
        return any(cpv.startswith(prefix) for prefix in self.cpv_prefixes)

    def has_certification(self, required: str) -> bool:
        """Case- and whitespace-insensitive membership check."""
        want = required.strip().casefold()
        return any(want == held.strip().casefold() for held in self.certifications)
