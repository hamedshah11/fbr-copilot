"""Claude computer-use fallback for a SINGLE failed field.

Used only when the deterministic locator fails for one field. The contract:
  * one field, one screenshot — never a whole-page autopilot;
  * keep only the last 3 screenshots in any LLM context (image pruning);
  * log token usage to the audit trail;
  * verify the field afterwards, and on doubt return ``False`` so the executor
    escalates to ``needs_human``.

This is intentionally a stub until the execute phase: the deterministic path is
what we build and harden first (CLAUDE.md: "Deterministic first").
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:  # pragma: no cover - typing only
    from playwright.async_api import Page

    from audit import AuditLogger
    from field_map import FieldMapping

# Sonnet 4.6 drives the computer-use loop (see CLAUDE.md cost discipline).
# Model id per the running environment.
MODEL = "claude-sonnet-4-6"

# Never send more than this many screenshots to the model at once.
MAX_SCREENSHOTS = 3


async def resolve_field(
    page: "Page",
    mapping: "FieldMapping",
    value: Any,
    audit: "AuditLogger",
) -> bool:
    """Attempt to fill one field via the computer-use fallback.

    Returns ``True`` if the field was set and verified, else ``False``.

    Not implemented yet — the deterministic executor escalates failures to
    ``needs_human`` until this lands in the execute phase.
    """
    raise NotImplementedError(
        "computer-use fallback is implemented in the execute phase; "
        "until then, failed fields escalate to needs_human"
    )
