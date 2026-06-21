"""Normalize: happy path and structured failure."""

from __future__ import annotations

import pytest

from normalize import NormalizationError, normalize
from schema import TaxReturn


def test_normalize_returns_taxreturn(sample_raw):
    tr = normalize(sample_raw)
    assert isinstance(tr, TaxReturn)
    assert tr.taxpayer_name == "Test Taxpayer"


def test_normalize_raises_with_field_detail():
    with pytest.raises(NormalizationError) as exc:
        normalize({"tax_year": 2025})  # missing required taxpayer_name + salary
    # structured errors are available for the API to surface
    locs = {".".join(str(p) for p in e["loc"]) for e in exc.value.errors}
    assert "taxpayer_name" in locs
    assert "salary" in locs
