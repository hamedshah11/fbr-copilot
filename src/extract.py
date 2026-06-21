"""Optional: extract TaxReturn fields from documents via Claude Haiku.

Produces values *with confidence flags* so low-confidence fields can be
surfaced for human review before they ever reach :func:`normalize.normalize`.
Extraction is metered: log token usage to the audit trail and cache the system
prompt (see CLAUDE.md cost discipline).

Stubbed until intake supports documents; the API accepts already-structured
data today.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel

# Haiku 4.5 handles document extraction (see CLAUDE.md). Model id per env.
MODEL = "claude-haiku-4-5-20251001"


class ExtractedField(BaseModel):
    """A single extracted value with provenance and a confidence score."""

    value: Any
    confidence: float  # 0.0 - 1.0; below threshold -> route to human review
    source: str | None = None  # e.g. document name / page


def extract_fields(documents: list[bytes]) -> dict[str, ExtractedField]:
    """Extract canonical fields from raw ``documents``.

    Returns a mapping of dotted canonical paths (matching :class:`TaxReturn`) to
    :class:`ExtractedField`. Not implemented yet.
    """
    raise NotImplementedError(
        "document extraction lands when intake accepts documents; "
        "use structured TaxReturn input for now"
    )
