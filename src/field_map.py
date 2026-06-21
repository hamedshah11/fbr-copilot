"""Load and validate IRIS field maps from ``config/iris_map/*.yaml``.

Field maps are the durable IP: they map canonical :class:`TaxReturn` fields to
IRIS tab / field / code plus a locator. **Selectors live ONLY in these YAML
files** — never inline in the executor.

IRIS is Oracle ADF: element ids are dynamic, so locators prefer
``role`` / ``label`` / ``text``. ``css`` / ``xpath`` are a last resort and must
carry a ``note`` explaining why they are pinned.
"""

from __future__ import annotations

from pathlib import Path

import yaml
from pydantic import BaseModel, ConfigDict, Field, model_validator

# config/iris_map lives at the repo root, two levels up from this file (src/).
CONFIG_DIR = Path(__file__).resolve().parent.parent / "config" / "iris_map"


class Locator(BaseModel):
    """How to find one IRIS element. Prefer role/label/text over css/xpath."""

    model_config = ConfigDict(extra="forbid")

    role: str | None = None  # ARIA role for get_by_role
    name: str | None = None  # accessible name, used with role
    label: str | None = None  # get_by_label
    text: str | None = None  # get_by_text
    css: str | None = None  # last resort — must set `note`
    xpath: str | None = None  # last resort — must set `note`
    note: str | None = None  # why this locator, especially for css/xpath

    @model_validator(mode="after")
    def _validate(self) -> "Locator":
        if not any([self.role, self.label, self.text, self.css, self.xpath]):
            raise ValueError(
                "locator needs at least one of role/label/text/css/xpath"
            )
        if (self.css or self.xpath) and not self.note:
            raise ValueError(
                "css/xpath locators must include a 'note' — ADF ids are dynamic, "
                "so pinned selectors need a reason"
            )
        return self


class FieldMapping(BaseModel):
    """Maps one canonical field to one IRIS input."""

    model_config = ConfigDict(extra="forbid")

    canonical: str  # dotted path into TaxReturn, e.g. "salary.taxable"
    tab: str  # IRIS tab/section the field lives on
    iris_field: str  # human label of the IRIS field
    code: str | None = None  # IRIS line code, when applicable
    input_type: str = "number"  # text | number | select | checkbox | readonly
    locator: Locator
    note: str | None = None


class FieldMap(BaseModel):
    """A complete field map for one return type."""

    model_config = ConfigDict(extra="forbid")

    return_type: str
    description: str | None = None
    fields: list[FieldMapping] = Field(min_length=1)


def load_field_map(return_type: str, *, config_dir: Path | None = None) -> FieldMap:
    """Load and validate the field map for ``return_type``.

    Args:
        return_type: base filename without extension, e.g. ``"salaried"``.
        config_dir: override the default ``config/iris_map`` directory (tests).

    Raises:
        FileNotFoundError: if no matching YAML file exists.
    """
    directory = config_dir or CONFIG_DIR
    path = directory / f"{return_type}.yaml"
    if not path.exists():
        raise FileNotFoundError(f"no field map for return_type={return_type!r} at {path}")
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    return FieldMap.model_validate(data)
