#!/usr/bin/env python3
"""SPIKE — throwaway. Drive ONE salaried return through FBR IRIS to a *saved
draft* and stop. It NEVER submits (no Submit/Verify/PIN — CLAUDE.md rule #1).

What it does:
  1. log in, pausing to ask a human for the OTP if IRIS demands one (never guessed);
  2. open the income-tax return for the tax year;
  3. fill the Salary tab, one withholding line, and two wealth-statement rows
     with hardcoded SAMPLE values;
  4. save as draft;
  5. record every locator it actually used into config/iris_map/salaried.draft.yaml;
  6. append a per-step log to docs/spike_notes.md (stable selector? or ambiguous
     → vision-fallback candidate);
  7. run with Playwright tracing on and save the trace.

Real runs need a headed browser + a human at the terminal for the OTP. Use
`--dry-run` to exercise all the plumbing offline against a local sample page —
no creds, no network, no OTP — which is what CI / a cloud box can verify.

    python scripts/spike_salaried.py --dry-run --headless \
        --out-map runs/dryrun/salaried.draft.yaml --notes runs/dryrun/spike_notes.md
    python scripts/spike_salaried.py            # real run, headed, uses .env
"""

from __future__ import annotations

import argparse
import asyncio
import datetime as dt
import os
import sys
import tempfile
from pathlib import Path
from typing import Any

import yaml
from playwright.async_api import Locator, Page, async_playwright
from playwright.async_api import TimeoutError as PWTimeout

try:
    from dotenv import load_dotenv
except ImportError:  # dotenv is optional
    load_dotenv = None

REPO = Path(__file__).resolve().parent.parent
DEFAULT_MAP = REPO / "config" / "iris_map" / "salaried.draft.yaml"
DEFAULT_NOTES = REPO / "docs" / "spike_notes.md"
DEFAULT_BASE_URL = "https://iris.fbr.gov.pk"

# Hardcoded SAMPLE values — fake, for the spike only. PKR whole rupees.
SAMPLE = {
    "salary_pay": 2_400_000,
    "salary_allowances": 600_000,
    "wht_salary_149": 5_000,
    "wealth_property": 7_000_000,
    "wealth_vehicle": 2_500_000,
}

# The fields to draft, each with an ORDERED ladder of locator candidates
# (role → label → text → css). The spike records which rung actually worked;
# that recording becomes config/iris_map/salaried.draft.yaml. In real IRIS these
# labels are best-guess hypotheses — discovering the right one is the point.
FIELDS: list[dict[str, Any]] = [
    {
        "canonical": "salary.pay",
        "tab": "Salary",
        "iris_field": "Pay, Wages or other remuneration",
        "code": "1009",
        "value": SAMPLE["salary_pay"],
        "candidates": [
            {"label": "Pay, Wages or other remuneration"},
            {"role": "textbox", "name": "Pay, Wages or other remuneration"},
            {"css": "input[id*='PayWages']", "note": "ADF id fragment — pin only if label/role fail"},
        ],
    },
    {
        "canonical": "salary.allowances",
        "tab": "Salary",
        "iris_field": "Allowances",
        "code": "1019",
        "value": SAMPLE["salary_allowances"],
        "candidates": [
            {"role": "textbox", "name": "Allowances"},
            {"label": "Allowances"},
        ],
    },
    {
        "canonical": "taxes.adjustable[0].amount",
        "tab": "Tax Chargeable / Payments",
        "iris_field": "Tax deducted on salary u/s 149",
        "code": "64020003",
        "value": SAMPLE["wht_salary_149"],
        "candidates": [
            {"label": "Tax deducted on salary"},
            {"css": "input[id*='wht-amt-64020003']", "note": "pinned by withholding code — dynamic ADF row"},
        ],
    },
    {
        "canonical": "wealth.assets[0].amount",
        "tab": "Wealth Statement / Assets",
        "iris_field": "Residential property",
        "code": "7001",
        "value": SAMPLE["wealth_property"],
        "candidates": [
            {"label": "Residential property"},
            {"role": "textbox", "name": "Residential property"},
        ],
    },
    {
        "canonical": "wealth.assets[1].amount",
        "tab": "Wealth Statement / Assets",
        "iris_field": "Motor vehicle",
        "code": "7002",
        "value": SAMPLE["wealth_vehicle"],
        "candidates": [
            {"label": "Motor vehicle"},
            {"role": "textbox", "name": "Motor vehicle"},
            {"css": "input[id*='MotorVehicle']", "note": "ADF id fragment"},
        ],
    },
]


def strategy_of(loc: dict[str, Any]) -> str:
    """Short name of a locator's strategy, for the step log."""
    for key in ("role", "label", "text", "css", "xpath"):
        if loc.get(key):
            return key
    return "?"


class StepLogger:
    """Appends the documented per-step record to docs/spike_notes.md."""

    def __init__(self, path: Path, dry_run: bool) -> None:
        self.path = Path(path)
        self.dry = dry_run
        self.blocks: list[str] = []

    def step(self, what: str, selector: str, status: str, note: str = "") -> None:
        block = f"[step] {what} — selector: {selector} — status: {status}"
        if note:
            block += f"\n  note: {note}"
        print(("DRY " if self.dry else "") + block, file=sys.stderr)
        self.blocks.append(block)

    def flush(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        stamp = dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")
        header = f"\n## Spike run {stamp}{' (dry-run)' if self.dry else ''}\n\n"
        with self.path.open("a", encoding="utf-8") as fh:
            fh.write(header + "\n".join(self.blocks) + "\n")


class LocatorRecorder:
    """Accumulates the winning locator per field → salaried.draft.yaml.

    Output matches the config/iris_map FieldMap shape so it can grow into the
    curated map once selectors are confirmed.
    """

    def __init__(self, path: Path, tax_year: int, dry_run: bool) -> None:
        self.path = Path(path)
        self.tax_year = tax_year
        self.dry = dry_run
        self.fields: list[dict[str, Any]] = []

    def record(self, field: dict[str, Any], locator: dict[str, Any], status: str, note: str) -> None:
        entry = {
            "canonical": field["canonical"],
            "tab": field["tab"],
            "iris_field": field["iris_field"],
            "code": field["code"],
            "input_type": "number",
            "status": status,  # ok | pinned | needs_fallback
            "locator": locator,
        }
        if note:
            entry["note"] = note
        self.fields.append(entry)

    def write(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        doc = {
            "return_type": "salaried",
            "description": (
                f"DRAFT map recorded by spike_salaried.py for TY{self.tax_year}"
                f"{' (DRY-RUN — sample selectors, not real IRIS)' if self.dry else ''}. "
                "Confirm each locator before promoting into salaried.yaml."
            ),
            "fields": self.fields,
        }
        banner = "# GENERATED by scripts/spike_salaried.py — do not hand-edit; re-run the spike.\n"
        with self.path.open("w", encoding="utf-8") as fh:
            fh.write(banner)
            yaml.safe_dump(doc, fh, sort_keys=False, allow_unicode=True)


def build_locator(page: Page, loc: dict[str, Any]) -> Locator:
    if loc.get("role"):
        name = loc.get("name")
        return page.get_by_role(loc["role"], name=name) if name else page.get_by_role(loc["role"])
    if loc.get("label"):
        return page.get_by_label(loc["label"])
    if loc.get("text"):
        return page.get_by_text(loc["text"])
    if loc.get("css"):
        return page.locator(loc["css"])
    if loc.get("xpath"):
        return page.locator("xpath=" + loc["xpath"])
    raise ValueError(f"empty locator candidate: {loc!r}")


async def smart_fill(
    page: Page, rec: LocatorRecorder, log: StepLogger, field: dict[str, Any], timeout_ms: int
) -> bool:
    """Try each candidate in order; record the first that fills. On total miss,
    mark the field a vision-fallback candidate (the spike does NOT call a model).
    """
    for loc in field["candidates"]:
        try:
            target = build_locator(page, loc).first
            await target.wait_for(state="visible", timeout=timeout_ms)
            await target.fill(str(field["value"]))
            # Commit ADF partial-page update by blurring the field.
            await target.evaluate("el => el.blur && el.blur()")
            strat = strategy_of(loc)
            status = "pinned" if strat in ("css", "xpath") else "ok"
            # The locator dict already carries its own `note`; don't duplicate it
            # at entry level. The step log still surfaces it for the human.
            rec.record(field, loc, status, "")
            log.step(f"fill {field['canonical']}", strat, status, loc.get("note", ""))
            return True
        except (PWTimeout, Exception):  # noqa: BLE001 - try the next rung
            continue
    # Nothing matched → escalate (in a real run) to a single-field vision fallback.
    fallback_loc = field["candidates"][0] if field["candidates"] else {}
    rec.record(field, fallback_loc, "needs_fallback", "no deterministic selector matched")
    log.step(
        f"fill {field['canonical']}",
        "fallback",
        "fallback",
        "no selector matched — would escalate to one-field vision fallback",
    )
    return False


async def wait_for_otp_via_file(
    otp_file: str, log: StepLogger, timeout_s: int = 300, poll_s: int = 2
) -> str:
    """Non-interactive OTP hand-off (e.g. a cloud session with no terminal):
    pause and poll a file the human writes the code into. Never guessed.
    """
    p = Path(otp_file)
    p.parent.mkdir(parents=True, exist_ok=True)
    if p.exists():
        p.unlink()
    print("\n" + "=" * 56, file=sys.stderr)
    print("  IRIS is asking for a one-time code (OTP).", file=sys.stderr)
    print(f"  Paused — write the code into:  {p}", file=sys.stderr)
    print("=" * 56, file=sys.stderr, flush=True)
    log.step("otp", "-", "waiting", f"polling {p} for a human-supplied code")
    waited = 0
    while waited < timeout_s:
        if p.exists():
            code = p.read_text(encoding="utf-8").strip()
            if code:
                p.unlink()
                return code
        await asyncio.sleep(poll_s)
        waited += poll_s
    raise SystemExit(f"timed out after {timeout_s}s waiting for OTP in {p}")


async def obtain_otp(log: StepLogger, otp_file: str | None) -> str:
    """Get the OTP from the human. Never guessed, never read from SMS."""
    if otp_file:
        return await wait_for_otp_via_file(otp_file, log)
    if sys.stdin.isatty():
        print("\n" + "=" * 56, file=sys.stderr)
        print("  IRIS is asking for a one-time code (OTP).", file=sys.stderr)
        print("  Check your phone/email and type it below. Never shared.", file=sys.stderr)
        print("=" * 56, file=sys.stderr)
        return input("  Enter OTP: ").strip()
    raise SystemExit(
        "OTP required but no interactive terminal. Re-run with --otp-file PATH so "
        "the code can be supplied out-of-band (e.g. from a cloud session)."
    )


async def handle_otp(page: Page, log: StepLogger, dry_run: bool, otp_file: str | None) -> None:
    if dry_run:
        log.step("otp", "-", "skipped", "dry-run")
        return
    otp_field = page.get_by_label("verification code")
    try:
        await otp_field.wait_for(state="visible", timeout=8000)
    except PWTimeout:
        log.step("otp", "-", "not-required")
        return
    code = await obtain_otp(log, otp_file)
    await otp_field.fill(code)
    await page.get_by_role("button", name="Verify").click()
    log.step("otp", "label 'verification code'", "ok", "entered by human")


async def login(page: Page, log: StepLogger, base_url: str, dry_run: bool, otp_file: str | None) -> None:
    cnic = os.environ.get("IRIS_CNIC")
    pwd = os.environ.get("IRIS_PASSWORD")
    if not dry_run and (not cnic or not pwd):
        raise SystemExit("set IRIS_CNIC and IRIS_PASSWORD in .env (never committed)")

    await page.goto(base_url)
    await page.get_by_label("Registration No").fill(cnic or "DRYRUN-CNIC")
    await page.get_by_label("Password").fill(pwd or "DRYRUN-PW")
    await page.get_by_role("button", name="Login").click()
    log.step("login", "label 'Registration No' + 'Password'", "ok",
             "credentials from .env; never logged")
    await handle_otp(page, log, dry_run, otp_file)


async def open_return(page: Page, log: StepLogger, tax_year: int) -> None:
    # Real IRIS navigation: Declaration → Income Tax Return → pick period → open
    # the 114(1) salaried form. Best-guess ladders; the spike confirms them.
    await page.get_by_role("link", name="Declaration").click()
    await page.get_by_role("link", name="Income Tax Return").click()
    await page.get_by_text(str(tax_year)).click()
    log.step("open-return", "text period", "ok", f"TY{tax_year}")


async def save_draft(page: Page, log: StepLogger) -> None:
    # Click Save ONLY. Never Submit/Verify/Confirm — those trigger the PIN and
    # are a human action by design.
    await page.get_by_role("button", name="Save").click()
    log.step("save-draft", "role button 'Save'", "ok", "draft only — never submitted")


def write_dryrun_page() -> str:
    """A tiny local page matching the FIELDS ladders, to exercise the plumbing.
    One field (Motor vehicle) intentionally has NO matching selector, to show
    the fallback-logging branch. Returns a file:// URL.
    """
    html = """<!doctype html><html><body>
      <h1>IRIS dry-run sample</h1>
      <label for="cnic">Registration No</label><input id="cnic">
      <label for="pwd">Password</label><input id="pwd" type="password">
      <button type="button">Login</button>
      <h2>Salary</h2>
      <label for="pay">Pay, Wages or other remuneration</label><input id="pay">
      <input aria-label="Allowances">
      <h2>Tax deducted</h2>
      <div>Tax deducted on salary</div><input id="wht-amt-64020003">
      <h2>Wealth statement</h2>
      <label for="prop">Residential property</label><input id="prop">
      <!-- 'Motor vehicle' deliberately absent → demonstrates fallback logging -->
      <label for="veh">Vehicle at cost</label><input id="veh">
      <button type="button">Save</button>
    </body></html>"""
    tmp = Path(tempfile.gettempdir()) / "iris_dryrun_sample.html"
    tmp.write_text(html, encoding="utf-8")
    return tmp.as_uri()


async def run(args: argparse.Namespace) -> int:
    if load_dotenv and (REPO / ".env").exists():
        load_dotenv(REPO / ".env")

    log = StepLogger(Path(args.notes), args.dry_run)
    rec = LocatorRecorder(Path(args.out_map), args.tax_year, args.dry_run)
    trace_out = Path(args.trace_out)
    timeout_ms = 2_000 if args.dry_run else 30_000
    base_url = write_dryrun_page() if args.dry_run else os.environ.get("IRIS_BASE_URL", DEFAULT_BASE_URL)

    async with async_playwright() as p:
        # SPIKE_BROWSER_EXEC lets a pinned/offline environment point at a cached
        # Chromium instead of the one bundled with the Playwright package.
        exec_path = os.environ.get("SPIKE_BROWSER_EXEC") or None
        browser = await p.chromium.launch(
            headless=args.headless, slow_mo=args.slow_mo, executable_path=exec_path
        )
        context = await browser.new_context()
        await context.tracing.start(screenshots=True, snapshots=True, sources=True)
        page = await context.new_page()
        page.set_default_timeout(timeout_ms)
        try:
            await login(page, log, base_url, args.dry_run, args.otp_file)
            if not args.dry_run:
                await open_return(page, log, args.tax_year)
            filled = 0
            for field in FIELDS:
                if await smart_fill(page, rec, log, field, timeout_ms):
                    filled += 1
            await save_draft(page, log)
            log.step("summary", "-", "ok",
                     f"{filled}/{len(FIELDS)} fields filled deterministically; rest → fallback")
            return 0
        finally:
            trace_out.parent.mkdir(parents=True, exist_ok=True)
            await context.tracing.stop(path=str(trace_out))
            await browser.close()
            rec.write()
            log.flush()
            print(f"\ntrace : {trace_out}\nmap   : {rec.path}\nnotes : {log.path}", file=sys.stderr)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    ap = argparse.ArgumentParser(description="Spike: draft one salaried IRIS return (never submits).")
    ap.add_argument("--dry-run", action="store_true", help="offline: local sample page, no creds/OTP/network")
    ap.add_argument("--headless", action="store_true", help="run headless (default: headed, for watching)")
    ap.add_argument("--slow-mo", type=int, default=0, help="ms delay between actions when watching")
    ap.add_argument("--tax-year", type=int, default=2025)
    ap.add_argument("--otp-file", default=None,
                    help="poll this file for the OTP (non-interactive / cloud) instead of prompting stdin")
    ap.add_argument("--out-map", default=str(DEFAULT_MAP), help="where to write the recorded draft field map")
    ap.add_argument("--notes", default=str(DEFAULT_NOTES), help="where to append the step log")
    ap.add_argument("--trace-out", default=None, help="trace zip path (default: traces/spike_salaried_<ts>.zip)")
    args = ap.parse_args(argv)
    if args.trace_out is None:
        stamp = dt.datetime.now().strftime("%Y%m%d-%H%M%S")
        args.trace_out = str(REPO / "traces" / f"spike_salaried_{stamp}.zip")
    return args


if __name__ == "__main__":
    raise SystemExit(asyncio.run(run(parse_args())))
