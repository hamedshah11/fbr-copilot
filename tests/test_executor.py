"""Executor helpers: canonical resolution and the retry wrapper."""

from __future__ import annotations

import pytest

from agent.executor import resolve_canonical
from agent.locators import with_retry
from normalize import normalize


def test_resolve_canonical_scalar_and_computed(sample_raw):
    tr = normalize(sample_raw)
    assert resolve_canonical(tr, "salary.pay") == 2_400_000
    assert resolve_canonical(tr, "salary.taxable") == 3_000_000  # computed field
    assert resolve_canonical(tr, "wealth.net_assets_current") == 10_000_000


def test_resolve_canonical_missing_path(sample_raw):
    tr = normalize(sample_raw)
    with pytest.raises(AttributeError):
        resolve_canonical(tr, "salary.nope")


async def test_with_retry_succeeds_after_failures():
    calls = {"n": 0}

    async def flaky():
        calls["n"] += 1
        if calls["n"] < 3:
            raise RuntimeError("transient")
        return "ok"

    result = await with_retry(flaky, retries=2, base_delay=0)
    assert result == "ok"
    assert calls["n"] == 3


async def test_with_retry_reraises_after_exhausting():
    async def always_fail():
        raise ValueError("boom")

    with pytest.raises(ValueError, match="boom"):
        await with_retry(always_fail, retries=1, base_delay=0)
