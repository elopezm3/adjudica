import json
from pathlib import Path

import pytest

FIXTURES = Path(__file__).parent / "fixtures"


def _load(name: str) -> dict:
    return json.loads((FIXTURES / name).read_text())


@pytest.fixture
def ted_tenders() -> dict:
    """Real TED response: eForms Spanish contract notices (2024-09)."""
    return _load("ted_tenders_eforms.json")


@pytest.fixture
def ted_awards() -> dict:
    """Real TED response: eForms Spanish award notices (2025-01)."""
    return _load("ted_awards_eforms.json")
