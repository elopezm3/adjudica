"""Qualification: can this company bid on this tender, and is it worth it?

Two layers, deliberately separated:
- eligibility.py — HARD rules (turnover, certifications, scope). Pure arithmetic and set
  membership, fully testable, no LLM. Failing one of these means you are legally
  disqualified, so there is nothing to reason about.
- (later) judgement — SOFT assessment (incumbent, price weight, margin). Needs reasoning
  and history; this is where the agent earns its keep.
"""
