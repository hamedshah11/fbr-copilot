"""ADF-safe locating helpers for Playwright.

Oracle ADF (IRIS) generates dynamic element ids, so we locate by
role / label / text first and fall back to css / xpath only when the field map
pins them with a reason. Everything here is async and wrapped with an explicit
timeout + retry; callers never loop forever.

Playwright is imported lazily / under ``TYPE_CHECKING`` so this module (and the
rest of ``src``) stays importable for unit tests without a browser installed.
"""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING, Awaitable, Callable, TypeVar

if TYPE_CHECKING:  # pragma: no cover - typing only
    from playwright.async_api import Locator as PWLocator
    from playwright.async_api import Page

    from field_map import Locator

T = TypeVar("T")

DEFAULT_TIMEOUT_MS = 15_000


async def locate(page: "Page", loc: "Locator", *, timeout_ms: int = DEFAULT_TIMEOUT_MS) -> "PWLocator":
    """Resolve a field-map :class:`~field_map.Locator` to a Playwright locator.

    Preference order matches the field-map convention: role → label → text →
    css → xpath. Waits for the element to be visible before returning.
    """
    if loc.role:
        target = (
            page.get_by_role(loc.role, name=loc.name)  # type: ignore[arg-type]
            if loc.name
            else page.get_by_role(loc.role)  # type: ignore[arg-type]
        )
    elif loc.label:
        target = page.get_by_label(loc.label)
    elif loc.text:
        target = page.get_by_text(loc.text)
    elif loc.css:
        target = page.locator(loc.css)
    elif loc.xpath:
        target = page.locator(f"xpath={loc.xpath}")
    else:  # pragma: no cover - field_map.Locator validation prevents this
        raise ValueError("empty locator")

    await target.wait_for(state="visible", timeout=timeout_ms)
    return target


async def with_retry(
    factory: Callable[[], Awaitable[T]],
    *,
    retries: int = 2,
    base_delay: float = 0.5,
    exceptions: tuple[type[BaseException], ...] = (Exception,),
) -> T:
    """Run ``factory()`` with exponential backoff. Re-raises the last error.

    ``factory`` is a zero-arg coroutine function so each attempt builds a fresh
    awaitable. Delays are ``base_delay * 2**attempt``; with ``base_delay=0`` the
    retries are immediate (useful in tests).
    """
    last: BaseException | None = None
    for attempt in range(retries + 1):
        try:
            return await factory()
        except exceptions as exc:
            last = exc
            if attempt == retries:
                break
            if base_delay:
                await asyncio.sleep(base_delay * (2**attempt))
    assert last is not None  # loop always sets `last` before breaking
    raise last
