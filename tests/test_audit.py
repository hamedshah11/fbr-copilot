"""Audit: PII masking and structured, token-aware logging."""

from __future__ import annotations

from audit import AuditLogger, Status, TokenUsage, mask_text, mask_value


def test_mask_value_passes_money_through():
    assert mask_value(350000) == 350000
    assert mask_value(1234.0) == 1234.0


def test_mask_value_masks_cnic():
    masked = mask_value("12345-1234567-1")
    assert "1234567" not in masked
    assert set(masked) <= {"*"}


def test_mask_value_sensitive_name():
    masked = mask_value("Test Taxpayer", sensitive=True)
    assert masked.startswith("T")
    assert "Taxpayer" not in masked


def test_mask_text_scrubs_patterns():
    out = mask_text("CNIC 12345-1234567-1 email a@b.com phone 03001234567")
    assert "12345-1234567-1" not in out
    assert "a@b.com" not in out
    assert "03001234567" not in out


def test_logger_masks_field_value_and_buffers(tmp_path):
    sink = tmp_path / "audit.jsonl"
    log = AuditLogger("job-1", sink=sink)
    log.field("fill:taxpayer_name", "taxpayer_name", "Test Taxpayer", sensitive=True)
    log.field("fill:salary.taxable", "salary.taxable", 3_000_000)

    assert len(log.events) == 2
    assert log.events[0].value_masked == "T***(13 chars)"
    assert log.events[1].value_masked == 3_000_000
    # JSONL sink has one line per event
    assert sink.read_text(encoding="utf-8").strip().count("\n") == 1


def test_logger_token_totals():
    log = AuditLogger("job-2")
    log.log("extract", usage=TokenUsage(model="m", tokens_in=10, tokens_out=4))
    log.log("fallback", usage=TokenUsage(model="m", tokens_in=20, tokens_out=6))
    assert log.total_tokens() == (30, 10)


def test_status_enum_values():
    assert Status.NEEDS_HUMAN.value == "needs_human"
