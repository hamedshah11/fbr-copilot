"""Schema: coercion, computed totals, and the secrets/PII guardrail."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from schema import SalaryIncome, TaxReturn, WealthStatement


def test_valid_return_parses(sample_raw):
    tr = TaxReturn.model_validate(sample_raw)
    assert tr.tax_year == 2025
    assert tr.return_type == "salaried"


def test_salary_computed_totals(sample_raw):
    tr = TaxReturn.model_validate(sample_raw)
    # pay 2,400,000 + allowances 600,000 = gross 3,000,000; exempt 0
    assert tr.salary.gross == 3_000_000
    assert tr.salary.taxable == 3_000_000


def test_wealth_reconciles_to_zero(sample_raw):
    tr = TaxReturn.model_validate(sample_raw)
    w = tr.wealth
    assert w is not None
    assert w.total_assets == 11_000_000
    assert w.total_liabilities == 1_000_000
    assert w.net_assets_current == 10_000_000
    # prior 8,000,000 + inflows 3,050,000 - outflows 1,050,000 == 10,000,000
    assert w.reconciliation_difference == 0


@pytest.mark.parametrize(
    "raw_amount,expected",
    [(1234, 1234), ("1,234", 1234), ("Rs 1,234", 1234), (1234.0, 1234)],
)
def test_pkr_coercion(raw_amount, expected):
    assert SalaryIncome(pay=raw_amount).pay == expected


@pytest.mark.parametrize("bad", [1234.5, "12.5", True, "abc", ""])
def test_pkr_rejects_non_integer(bad):
    with pytest.raises(ValidationError):
        SalaryIncome(pay=bad)


def test_extra_fields_forbidden(sample_raw):
    sample_raw["salary"]["typo_field"] = 1
    with pytest.raises(ValidationError):
        TaxReturn.model_validate(sample_raw)


@pytest.mark.parametrize("cnic", ["1234567890123", "12345-1234567-1"])
def test_taxpayer_name_rejects_cnic(sample_raw, cnic):
    sample_raw["taxpayer_name"] = cnic
    with pytest.raises(ValidationError, match="CNIC"):
        TaxReturn.model_validate(sample_raw)


@pytest.mark.parametrize("year", [2014, 2101])
def test_tax_year_bounds(sample_raw, year):
    sample_raw["tax_year"] = year
    with pytest.raises(ValidationError):
        TaxReturn.model_validate(sample_raw)


def test_wealth_optional():
    tr = TaxReturn(tax_year=2025, taxpayer_name="Jane Test", salary=SalaryIncome(pay=100))
    assert tr.wealth is None
    assert isinstance(WealthStatement(), WealthStatement)
