"""Drive IRIS to draft a return from a validated TaxReturn + field map.

DETERMINISTIC FIRST: every field is driven via Playwright using the locators in
the field map. The Claude vision fallback (``agent/fallback.py``) is used only
when a real selector fails for a single field — never as the default path.

NEVER SUBMITS. This executor only fills fields and saves drafts. The final
PIN / OTP submission on IRIS is always a human action, by design.

Per-field control flow::

    assert expected page/tab state
      -> act (with timeout + retry)
        -> screenshot
          -> audit log
    on repeated failure -> single-field vision fallback
      -> still failing  -> flag needs_human (never loop forever)

The concrete Playwright interactions (asserting ADF tab state, typing into ADF
inputs, capturing screenshots) are stubbed for the execute phase; the
control-flow skeleton, value resolution, and escalation are real and tested.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import TYPE_CHECKING, Any

from pydantic import BaseModel

if TYPE_CHECKING:  # pragma: no cover - typing only
    from playwright.async_api import Page

from audit import AuditLogger, Status
from field_map import FieldMap, FieldMapping


class FieldOutcome(str, Enum):
    OK = "ok"
    FALLBACK = "fallback"
    NEEDS_HUMAN = "needs_human"


@dataclass
class FieldResult:
    field: str
    outcome: FieldOutcome
    value: Any
    message: str | None = None


def resolve_canonical(model: BaseModel, path: str) -> Any:
    """Resolve a dotted ``path`` (e.g. ``"salary.taxable"``) against ``model``.

    Walks attribute access, so computed fields (``salary.taxable``,
    ``wealth.net_assets_current``) resolve just like stored ones. Raises
    ``AttributeError`` if any segment is missing.
    """
    current: Any = model
    for part in path.split("."):
        current = getattr(current, part)
    return current


class Executor:
    """Fills IRIS fields from a TaxReturn using a field map. Drafts only."""

    def __init__(
        self,
        page: "Page",
        audit: AuditLogger,
        *,
        timeout_ms: int = 15_000,
        retries: int = 2,
        headed: bool = False,
    ) -> None:
        self.page = page
        self.audit = audit
        self.timeout_ms = timeout_ms
        self.retries = retries
        self.headed = headed

    async def run(self, tax_return: BaseModel, field_map: FieldMap) -> list[FieldResult]:
        """Draft every mapped field. Returns a per-field result for review."""
        results: list[FieldResult] = []
        for mapping in field_map.fields:
            value = resolve_canonical(tax_return, mapping.canonical)
            results.append(await self._fill_field(mapping, value))
        return results

    async def _fill_field(self, mapping: FieldMapping, value: Any) -> FieldResult:
        # Deterministic path: assert state -> act -> screenshot -> log, with retry.
        for attempt in range(self.retries + 1):
            try:
                await self._assert_tab(mapping.tab)
                await self._set_value(mapping, value)
                shot = await self._screenshot(mapping)
                self.audit.field(
                    step=f"fill:{mapping.canonical}",
                    field=mapping.canonical,
                    value=value,
                    status=Status.OK,
                    page_state=mapping.tab,
                    screenshot_ref=shot,
                )
                return FieldResult(mapping.canonical, FieldOutcome.OK, value)
            except Exception as exc:  # noqa: BLE001 - escalate, never crash the run
                self.audit.field(
                    step=f"fill:{mapping.canonical}",
                    field=mapping.canonical,
                    value=value,
                    status=Status.RETRY,
                    page_state=mapping.tab,
                    note=f"attempt {attempt + 1} failed: {exc}",
                )

        # Escalate to the single-field vision fallback.
        try:
            from agent.fallback import resolve_field

            if await resolve_field(self.page, mapping, value, self.audit):
                self.audit.field(
                    step=f"fill:{mapping.canonical}",
                    field=mapping.canonical,
                    value=value,
                    status=Status.FALLBACK,
                    page_state=mapping.tab,
                )
                return FieldResult(mapping.canonical, FieldOutcome.FALLBACK, value)
        except Exception as exc:  # noqa: BLE001 - fallback failure also escalates
            self.audit.field(
                step=f"fill:{mapping.canonical}",
                field=mapping.canonical,
                value=value,
                status=Status.RETRY,
                note=f"fallback failed: {exc}",
            )

        # Give up cleanly: flag for a human, do not loop forever.
        self.audit.field(
            step=f"fill:{mapping.canonical}",
            field=mapping.canonical,
            value=value,
            status=Status.NEEDS_HUMAN,
            page_state=mapping.tab,
        )
        return FieldResult(
            mapping.canonical,
            FieldOutcome.NEEDS_HUMAN,
            value,
            message="deterministic locator and fallback both failed",
        )

    # --- IRIS interactions (stubbed for the execute phase) -----------------

    async def _assert_tab(self, tab: str) -> None:
        """Assert IRIS is on the expected tab/section before acting."""
        raise NotImplementedError("IRIS tab assertion lands in the execute phase")

    async def _set_value(self, mapping: FieldMapping, value: Any) -> None:
        """Locate the field and set ``value`` (ADF-safe), per its input_type."""
        raise NotImplementedError("IRIS field set lands in the execute phase")

    async def _screenshot(self, mapping: FieldMapping) -> str:
        """Capture a screenshot and return its reference for the audit log."""
        raise NotImplementedError("screenshot capture lands in the execute phase")
