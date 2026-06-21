# fbr-copilot

Drafts a person's income-tax return on FBR's IRIS portal from structured tax
data. **It drafts and saves only — it never submits.** A human reviews the
draft and submits (entering the PIN/OTP) themselves.

See [`CLAUDE.md`](./CLAUDE.md) for the full spec and the non-negotiable hard
rules. Phase 1 scope: **salaried + wealth statement**.

## Pipeline

```
intake → normalize → field-map → execute → review → audit
```

## Layout

```
config/iris_map/   YAML field maps (the durable IP — selectors live ONLY here)
src/
  schema.py        canonical TaxReturn (pydantic)
  normalize.py     raw input → validated TaxReturn
  extract.py       optional: docs → fields via Claude Haiku (stub)
  field_map.py     load + validate config/iris_map/*.yaml
  audit.py         masked, structured, token-aware logging
  api.py           FastAPI: create / status / approve  (approve != submit)
  agent/
    executor.py    drives IRIS from a TaxReturn + field map (drafts only)
    locators.py    ADF-safe async locating helpers
    fallback.py    single-field Claude computer-use fallback (stub)
fixtures/          sample (fake) TaxReturn inputs
tests/             pytest suite
docs/              PROGRESS.md, spike_notes.md, lovable_brief.md
scripts/           throwaway spike_*.py exploration scripts
```

## Setup

```bash
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
# heavy runtime deps (playwright/anthropic/supabase) are only needed to run the
# agent, not the unit tests; for the agent also:
#   playwright install chromium
cp .env.example .env   # then fill in — secrets live ONLY here, never committed
```

## Run

```bash
# tests (src is the import root via pyproject pythonpath)
pytest

# job API
PYTHONPATH=src uvicorn api:app --reload
#   POST /returns           create a drafting job (body: {"tax_return": {...}})
#   GET  /returns/{id}      status + per-field review diff
#   POST /returns/{id}/approve   mark reviewed (NEVER submits)
```

## Safety

CNIC / IRIS password / PIN are credentials — they live in `.env` only and are
never written to code, git, fixtures, or audit logs. Audit logs store masked
values and per-field status. Develop only against a test / your-own IRIS
account, never a real client's live account.
