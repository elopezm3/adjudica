"""Smoke test: the package imports and declares a version."""

import adjudica


def test_package_imports() -> None:
    assert adjudica.__version__
