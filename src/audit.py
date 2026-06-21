"""Masked, structured audit logging for every IRIS action.

Each record captures (see CLAUDE.md):
  * step name + page state
  * the field touched and its **masked** value (never raw PII / secrets)
  * a screenshot reference
  * the IRIS response / outcome status
  * token usage (in/out) per LLM call, so cost is queryable

Masking rules:
  * CNIC, password and PIN should never reach this module — but we defensively
    mask anything that looks like a CNIC, email, or phone number.
  * Free-text values are scrubbed for those patterns.
  * Money amounts are logged as-is (they are the point of the per-field diff);
    it is the identifying data *around* them that gets masked.
  * Callers mark identity fields (e.g. taxpayer_name) ``sensitive=True`` so the
    value is reduced to a non-identifying hint.

This module writes newline-delimited JSON (JSONL). Persisting to Supabase is a
later step; the JSONL sink and in-memory buffer are the durable interface now.
"""

from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

# --- masking ---------------------------------------------------------------

_CNIC_RE = re.compile(r"\b\d{5}-?\d{7}-?\d\b")
_EMAIL_RE = re.compile(r"\b[\w.+-]+@[\w-]+\.[\w.-]+\b")
_PHONE_RE = re.compile(r"\b(?:\+?92|0)\d{9,10}\b")
_COMPACT = re.compile(r"[\s-]")


def _mask_digits(s: str, keep: int = 0) -> str:
    """Replace all but the last ``keep`` characters with ``*``."""
    if keep <= 0 or len(s) <= keep:
        return "*" * len(s)
    return "*" * (len(s) - keep) + s[-keep:]


def _mask_email(email: str) -> str:
    local, _, domain = email.partition("@")
    head = local[0] if local else ""
    return f"{head}***@{domain}"


def mask_text(text: str) -> str:
    """Scrub CNIC / email / phone patterns out of free-form text."""
    text = _CNIC_RE.sub("***-CNIC-***", text)
    text = _EMAIL_RE.sub(lambda m: _mask_email(m.group()), text)
    text = _PHONE_RE.sub(lambda m: _mask_digits(m.group()), text)
    return text


def mask_value(value: Any, *, sensitive: bool = False) -> Any:
    """Return a log-safe version of ``value``.

    Numbers pass through (money is logged). Strings are scrubbed for PII
    patterns. ``sensitive=True`` reduces any value to a non-identifying hint
    (first char + length), for fields like ``taxpayer_name``.
    """
    if value is None:
        return None
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return value

    s = str(value)
    if sensitive:
        head = s[0] if s else ""
        return f"{head}***({len(s)} chars)"

    compact = _COMPACT.sub("", s)
    # A bare CNIC or any long digit run → mask aggressively.
    if _CNIC_RE.fullmatch(s) or (compact.isdigit() and len(compact) >= 9):
        return _mask_digits(compact)
    return mask_text(s)


# --- structured events -----------------------------------------------------


class Status(str, Enum):
    """Outcome of a single audited action."""

    OK = "ok"
    RETRY = "retry"
    FALLBACK = "fallback"
    NEEDS_HUMAN = "needs_human"
    ERROR = "error"


class TokenUsage(BaseModel):
    model: str
    tokens_in: int = 0
    tokens_out: int = 0
    est_cost_usd: float | None = None  # filled by caller's pricing, if any


class AuditEvent(BaseModel):
    """One masked, structured audit record."""

    timestamp: str = Field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )
    job_id: str
    step: str
    status: Status = Status.OK
    page_state: str | None = None
    field: str | None = None  # canonical field path, e.g. "salary.taxable"
    value_masked: Any | None = None
    screenshot_ref: str | None = None
    iris_response: str | None = None
    usage: TokenUsage | None = None
    note: str | None = None


class AuditLogger:
    """Collects :class:`AuditEvent` records, masking values on the way in.

    Events are buffered in memory and, if ``sink`` is given, appended as JSONL.
    """

    def __init__(self, job_id: str, sink: Path | None = None) -> None:
        self.job_id = job_id
        self.sink = Path(sink) if sink else None
        self.events: list[AuditEvent] = []
        if self.sink:
            self.sink.parent.mkdir(parents=True, exist_ok=True)

    def log(self, step: str, **fields: Any) -> AuditEvent:
        """Record an event for this job. ``fields`` map onto AuditEvent."""
        event = AuditEvent(job_id=self.job_id, step=step, **fields)
        self.events.append(event)
        if self.sink:
            with self.sink.open("a", encoding="utf-8") as fh:
                fh.write(event.model_dump_json() + "\n")
        return event

    def field(
        self,
        step: str,
        field: str,
        value: Any,
        *,
        sensitive: bool = False,
        **fields: Any,
    ) -> AuditEvent:
        """Record a field interaction with the value masked before storage."""
        return self.log(
            step,
            field=field,
            value_masked=mask_value(value, sensitive=sensitive),
            **fields,
        )

    def total_tokens(self) -> tuple[int, int]:
        """Return ``(tokens_in, tokens_out)`` summed across logged usage."""
        tin = sum(e.usage.tokens_in for e in self.events if e.usage)
        tout = sum(e.usage.tokens_out for e in self.events if e.usage)
        return tin, tout
