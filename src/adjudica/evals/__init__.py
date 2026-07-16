"""Phase 0: golden-set builder and eval harness.

Ground truth sources (independent of the system under test):
- Extraction: eForms XML fields published alongside the PDF pliegos.
- Outcomes: award notices linked by procedure UUID (cbc:ContractFolderID / BT-04).

Outcome labels are three-state: awarded / desierto / unknown. Never collapse
"no award notice found" into a negative.
"""
