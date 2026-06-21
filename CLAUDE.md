# FBR IRIS Return-Drafting Agent

A service that takes a person's structured tax data and drafts their income tax return on FBR's IRIS portal. **It never submits.** A human reviews and submits.

This file is loaded every session. Keep it dense. Read it before planning anything.

## Hard rules — never violate

1. **Never submit a return.** The agent drafts and saves only. Submission (the final PIN/OTP step) is always a human action, by design — it is both safer for liability and sidesteps reading the taxpayer's SMS.
2. **Never store or log secrets.** CNIC, IRIS passwords, and PINs live in env/secrets only — never in code, git, fixtures, or audit logs.
3. **Mask PII in audit logs.** Store field status and masked values, not raw taxpayer data in plaintext.
4. **Deterministic first.** Drive IRIS with Playwright. Use the Claude vision/computer-use fallback only when a real selector fails, never as the default path.
5. **Every IRIS action is logged before it is taken**, and must be reversible (draft state).
6. **OTP/PIN → pause, don't guess.** When IRIS demands a code, stop and surface it to the human. The agent never fabricates or brute-forces a code.
7. **Never develop against a real client's live account.** Use a test/your-own account on a non-production basis.

## Architecture

```
intake → normalize → field-map → execute → review → audit
```

* **intake** — structured `TaxReturn` JSON, or documents to be parsed
* **normalize** — validate + coerce into the canonical schema (`src/schema.py`)
* **field-map** — config mapping canonical fields → IRIS tab/field/code (`config/iris_map/*.yaml`). This is the durable IP: data, not code. Same across every taxpayer.
* **execute** — the worker that drives IRIS (`src/agent/`), hybrid Playwright + Claude fallback
* **review** — produces a saved draft + a per-field diff for human approval
* **audit** — structured record of every action: step, masked field value, screenshot ref, IRIS response, token cost

## Tech stack

* Python 3.12, Playwright (async), FastAPI for the job API
* Anthropic SDK — Haiku 4.5 for document extraction, Sonnet 4.6 (computer-use) for navigation fallback
* Supabase (Postgres) — shared store + job queue; the worker claims jobs and writes results back
* Pydantic for the schema, pytest for tests, Playwright trace viewer for debugging IRIS

## Project layout

```
config/iris_map/        # YAML field maps, one per return type — selectors live ONLY here
src/
  schema.py             # canonical TaxReturn (pydantic)
  normalize.py          # raw input → validated TaxReturn
  extract.py            # optional: docs → fields via Haiku, with confidence flags
  agent/
    executor.py         # drives IRIS using the field map
    fallback.py         # Claude computer-use fallback for a single failed field
    locators.py         # helpers for ADF-safe locating
  audit.py              # masked, structured logging incl. token usage
  api.py                # FastAPI: create / status / approve  (approve != submit)
scripts/spike_*.py      # throwaway exploration scripts
fixtures/               # sample TaxReturn inputs
docs/                   # spike_notes.md, lovable_brief.md, PROGRESS.md
tests/
```

## Conventions

* Selectors live in `config/iris_map`, never inline. IRIS is Oracle ADF — element IDs are dynamic. Prefer `get_by_role`, `get_by_label`, `get_by_text`; treat CSS/xpath as last resort and pin them in the map with a comment.
* Each execute step does: assert expected page state → act → screenshot → log, then continue.
* Wrap every IRIS interaction with an explicit timeout + retry. On repeated failure: escalate to the vision fallback (one field, one screenshot), then to a `needs_human` flag. Never loop forever.
* Money fields are PKR integers, no floats. Withholding lines are `{code, description, amount}`.
* Headless by default; a `--headed` flag for watching.

## Cost discipline (this is a metered system)

* Loop model Sonnet 4.6, extraction Haiku 4.5.
* Image pruning: keep only the last 3 screenshots in any LLM context.
* Prompt caching on the system prompt + the IRIS field map.
* Log tokens-in / tokens-out per run to the audit table so cost is queryable.

## Out of scope until told otherwise

Multi-tenant auth, billing, the Lovable UI (phase 3+), any auto-submit (ever), return types beyond salaried (phase 1 is salaried + wealth statement only).

When a phase finishes, write a short summary to `docs/PROGRESS.md` before clearing context.
