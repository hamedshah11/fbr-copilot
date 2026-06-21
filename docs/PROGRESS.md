# Progress

## Phase 0 — Scaffold (2026-06-21)

Project skeleton stood up from `CLAUDE.md`. Repo is buildable and the unit
suite is green (44 tests, no browser/network/LLM needed — heavy runtime deps
are imported lazily).

**Landed**

- `src/schema.py` — canonical `TaxReturn` (salaried + wealth statement). PKR is
  int-only (coerces `"1,234"`/`1234.0`, rejects fractions). Computed totals:
  salary gross/taxable, wealth net assets + reconciliation difference.
  `extra="forbid"`; `taxpayer_name` rejects CNIC-shaped values (secrets rule).
- `src/normalize.py` — `normalize(raw) -> TaxReturn`, `NormalizationError` with
  field-level detail.
- `src/field_map.py` — load + validate `config/iris_map/*.yaml`; locators prefer
  role/label/text, css/xpath require a `note`.
- `src/audit.py` — PII masking (CNIC/email/phone), `AuditLogger` (JSONL + buffer),
  token totals.
- `src/agent/` — `executor.py` (per-field deterministic → fallback → needs_human
  control flow; IRIS interactions stubbed), `locators.py` (ADF-safe async locate +
  retry/backoff), `fallback.py` (single-field computer-use stub).
- `src/api.py` — FastAPI create / status / approve. **No submit endpoint** (test
  asserts this); approve only transitions a `drafted` job.
- `config/iris_map/{salaried,wealth_statement}.yaml` — placeholder field maps
  (locators to be confirmed via spike).
- `fixtures/salaried_example.json` — fake, reconciles to zero.
- Tooling: `pyproject.toml` (deps + `pythonpath=["src"]`, asyncio auto),
  `.gitignore` (secrets + run artifacts), `.env.example`.

**Deliberately stubbed (raise `NotImplementedError`)**

- `extract.py` (Haiku document extraction), `agent/fallback.py` (computer-use),
  executor's concrete IRIS interactions (`_assert_tab`/`_set_value`/`_screenshot`).

**Not started**

- IRIS driving + login/OTP, Supabase queue/worker, document intake, the Lovable UI.

**Next**

- Spike one salaried return through IRIS (`scripts/spike_salaried.py`) to capture
  real ADF selectors into `config/iris_map/salaried.draft.yaml`.
