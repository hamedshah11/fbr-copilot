"""Canonical TaxReturn schema for the FBR IRIS return-drafting agent.

Phase 1 scope: salaried individual + wealth statement.

Secrets / PII policy (see CLAUDE.md):
  * CNIC, IRIS password, and PIN are login *credentials*. They are NOT part
    of this schema. They are supplied at execution time from env/secrets only
    and must never appear in code, git, fixtures, or audit logs.
  * Once logged in, IRIS pre-fills the taxpayer's CNIC / NTN on the return, so
    the return payload itself never needs to carry them.
  * ``taxpayer_name`` is PII but not a secret. It must be masked in audit logs
    (see ``src/audit.py``). Fixtures must use clearly fake names.

Money policy:
  * All amounts are PKR whole rupees as Python ``int`` — never floats.
    The ``PKR`` type coerces int-valued strings/floats (e.g. ``"1,234"`` or
    ``1234.0``) but rejects fractional values.
"""

from __future__ import annotations

import re
from typing import Annotated, Literal

from pydantic import (
    BaseModel,
    BeforeValidator,
    ConfigDict,
    Field,
    computed_field,
    field_validator,
)


def _to_pkr(value: object) -> object:
    """Coerce an incoming value to a whole-rupee ``int``, rejecting fractions."""
    if isinstance(value, bool):  # bool is an int subclass — reject explicitly
        raise ValueError("PKR amount must be a number, not a boolean")
    if isinstance(value, str):
        cleaned = value.replace(",", "").replace("PKR", "").replace("Rs", "").strip()
        if not cleaned:
            raise ValueError("PKR amount string is empty")
        value = float(cleaned)
    if isinstance(value, float):
        if not value.is_integer():
            raise ValueError(f"PKR amounts must be whole rupees, got {value!r}")
        return int(value)
    return value


# A monetary amount in Pakistani Rupees — whole rupees only, stored as ``int``.
PKR = Annotated[int, BeforeValidator(_to_pkr)]

# CNIC compact form is exactly 13 digits (optionally dashed: 12345-1234567-1).
_CNIC_COMPACT = re.compile(r"^\d{13}$")


class _Base(BaseModel):
    # Reject unknown keys so typos in intake surface immediately at normalize().
    model_config = ConfigDict(extra="forbid")


class LineItem(_Base):
    """Generic ``{code, description, amount}`` row.

    Used for withholding / adjustable / final-tax lines and for wealth-statement
    assets, liabilities, inflows and outflows. ``code`` is the IRIS line code
    that the field map ties to a concrete IRIS field.
    """

    code: str
    description: str
    amount: PKR


# CLAUDE.md names withholding lines explicitly as {code, description, amount};
# keep a readable alias for that use.
WithholdingLine = LineItem


class SalaryIncome(_Base):
    """Income from salary (IRIS salary section)."""

    employer_name: str | None = None
    pay: PKR = 0  # basic pay, wages, other remuneration
    allowances: PKR = 0  # taxable allowances
    perquisites: PKR = 0  # value of perquisites / benefits
    bonus: PKR = 0
    gratuity: PKR = 0
    leave_encashment: PKR = 0
    other: PKR = 0  # any other taxable salary component
    exempt: PKR = 0  # exempt portion of salary income

    @computed_field  # type: ignore[prop-decorator]
    @property
    def gross(self) -> int:
        return (
            self.pay
            + self.allowances
            + self.perquisites
            + self.bonus
            + self.gratuity
            + self.leave_encashment
            + self.other
        )

    @computed_field  # type: ignore[prop-decorator]
    @property
    def taxable(self) -> int:
        return max(self.gross - self.exempt, 0)


class OtherIncome(_Base):
    """Common non-salary income lines for a salaried filer."""

    profit_on_debt: PKR = 0  # bank / savings profit (often final/fixed tax)
    dividend: PKR = 0
    rent: PKR = 0
    capital_gains: PKR = 0
    other: PKR = 0


class TaxesPaid(_Base):
    """Tax already deducted/collected at source, by category."""

    salary_tax_withheld: PKR = 0  # tax deducted by the employer
    adjustable: list[LineItem] = Field(default_factory=list)  # adjustable WHT lines
    final: list[LineItem] = Field(default_factory=list)  # final / fixed-tax lines

    @computed_field  # type: ignore[prop-decorator]
    @property
    def total_adjustable(self) -> int:
        return self.salary_tax_withheld + sum(li.amount for li in self.adjustable)

    @computed_field  # type: ignore[prop-decorator]
    @property
    def total_final(self) -> int:
        return sum(li.amount for li in self.final)


class WealthStatement(_Base):
    """Wealth statement + reconciliation.

    Reconciliation identity (IRIS 7000 series)::

        prior_year_net_assets + total_inflows - total_outflows == net_assets_current

    A non-zero ``reconciliation_difference`` must be explained before filing.
    """

    assets: list[LineItem] = Field(default_factory=list)
    liabilities: list[LineItem] = Field(default_factory=list)
    prior_year_net_assets: PKR = 0

    # Inflows (sources of funds during the year)
    income_for_the_year: PKR = 0  # total income declared for the year
    other_inflows: list[LineItem] = Field(default_factory=list)

    # Outflows (application of funds)
    personal_expenses: PKR = 0
    other_outflows: list[LineItem] = Field(default_factory=list)

    @computed_field  # type: ignore[prop-decorator]
    @property
    def total_assets(self) -> int:
        return sum(a.amount for a in self.assets)

    @computed_field  # type: ignore[prop-decorator]
    @property
    def total_liabilities(self) -> int:
        return sum(li.amount for li in self.liabilities)

    @computed_field  # type: ignore[prop-decorator]
    @property
    def net_assets_current(self) -> int:
        return self.total_assets - self.total_liabilities

    @computed_field  # type: ignore[prop-decorator]
    @property
    def total_inflows(self) -> int:
        return self.income_for_the_year + sum(i.amount for i in self.other_inflows)

    @computed_field  # type: ignore[prop-decorator]
    @property
    def total_outflows(self) -> int:
        return self.personal_expenses + sum(o.amount for o in self.other_outflows)

    @computed_field  # type: ignore[prop-decorator]
    @property
    def reconciliation_difference(self) -> int:
        expected = (
            self.prior_year_net_assets + self.total_inflows - self.total_outflows
        )
        return self.net_assets_current - expected


class TaxReturn(_Base):
    """A validated income-tax return, ready for the field-map executor."""

    tax_year: int = Field(ge=2015, le=2100)
    taxpayer_name: str = Field(min_length=1)  # PII — mask in logs; never a CNIC
    return_type: Literal["salaried"] = "salaried"

    salary: SalaryIncome
    other_income: OtherIncome = Field(default_factory=OtherIncome)
    taxes: TaxesPaid = Field(default_factory=TaxesPaid)
    wealth: WealthStatement | None = None

    @field_validator("taxpayer_name")
    @classmethod
    def _reject_cnic_like(cls, v: str) -> str:
        compact = re.sub(r"[\s-]", "", v)
        if _CNIC_COMPACT.match(compact):
            raise ValueError(
                "taxpayer_name looks like a CNIC — CNIC is a secret credential "
                "and must never be stored in the return payload"
            )
        return v
