"""Shared test fixtures."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
FIXTURES = REPO_ROOT / "fixtures"


@pytest.fixture
def sample_raw() -> dict:
    """Raw salaried return as it would arrive at intake."""
    return json.loads((FIXTURES / "salaried_example.json").read_text(encoding="utf-8"))
