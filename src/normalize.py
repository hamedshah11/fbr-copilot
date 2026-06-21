"""Normalize raw intake into a validated canonical :class:`TaxReturn`.

Raw input may arrive as JSON from the API, from a form, or from the optional
document-extraction step. Normalization is the *single* place where loose
values are coerced and the schema is enforced, so everything downstream
(field-map, executor, audit) can trust the data without re-checking it.
"""

from __future__ import annotations

from typing import Any

from pydantic import ValidationError

from schema import TaxReturn


class NormalizationError(ValueError):
    """Raised when raw intake cannot be coerced into a valid :class:`TaxReturn`.

    Carries the structured pydantic error list on ``.errors`` so the API can
    return field-level detail to the caller.
    """

    def __init__(self, errors: list[dict[str, Any]]) -> None:
        self.errors = errors
        super().__init__(self._format(errors))

    @staticmethod
    def _format(errors: list[dict[str, Any]]) -> str:
        lines = [
            f"  - {'.'.join(str(p) for p in e.get('loc', ()))}: {e.get('msg', '')}"
            for e in errors
        ]
        return "TaxReturn validation failed:\n" + "\n".join(lines)


def normalize(raw: dict[str, Any]) -> TaxReturn:
    """Validate and coerce ``raw`` into a canonical :class:`TaxReturn`.

    Raises:
        NormalizationError: with field-level detail when validation fails.
    """
    try:
        return TaxReturn.model_validate(raw)
    except ValidationError as exc:
        raise NormalizationError(exc.errors()) from exc
