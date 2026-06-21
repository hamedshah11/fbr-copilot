"""IRIS execution layer: drives the portal from a validated TaxReturn.

Hybrid by design — deterministic Playwright first (``executor`` + ``locators``),
with a single-field Claude computer-use ``fallback`` only when a real selector
fails. Nothing here ever submits a return.
"""
