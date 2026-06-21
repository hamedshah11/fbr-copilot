"""Field maps: the shipped YAML validates and locator rules are enforced."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from field_map import FieldMap, Locator, load_field_map
from schema import TaxReturn

REQUIRED_TOP_LEVEL = {"salary", "other_income", "taxes", "wealth"}


@pytest.mark.parametrize("return_type", ["salaried", "wealth_statement"])
def test_shipped_maps_validate(return_type):
    fm = load_field_map(return_type)
    assert isinstance(fm, FieldMap)
    assert fm.fields, "field map must have at least one field"


@pytest.mark.parametrize("return_type", ["salaried", "wealth_statement"])
def test_canonical_paths_point_at_schema(return_type):
    """Every canonical path's first segment is a real TaxReturn field."""
    fm = load_field_map(return_type)
    for mapping in fm.fields:
        head = mapping.canonical.split(".")[0]
        assert head in TaxReturn.model_fields or head in REQUIRED_TOP_LEVEL


def test_missing_map_raises():
    with pytest.raises(FileNotFoundError):
        load_field_map("does_not_exist")


def test_locator_requires_a_selector():
    with pytest.raises(ValidationError):
        Locator()


def test_css_locator_requires_note():
    with pytest.raises(ValidationError, match="note"):
        Locator(css="#someAdfId")
    # with a note it is allowed
    assert Locator(css="#someAdfId", note="pinned: stable across sessions").css
