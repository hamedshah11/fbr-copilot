# Running the salaried spike against real IRIS (cloud session)

Throwaway spike. Drives ONE salaried return to a **saved draft** on FBR IRIS and
stops. **It never submits** — the final PIN/OTP submission is always a human
action. See `scripts/spike_salaried.py` and `CLAUDE.md`.

## Before you start
- **Network:** the cloud environment's *Network access* must be **Custom** with
  `iris.fbr.gov.pk` and `*.fbr.gov.pk` in *Allowed domains* (keep "include
  default package managers" ticked). Environment changes apply to **new**
  sessions — reconfigure, then start a fresh session.
- **Account:** use a **test / your-own** IRIS account — never a real client's.
- **Secrets rule:** credentials go in a runtime `.env` only (already gitignored).
  Do NOT put them in the environment's *Environment variables* box or the setup
  script — those are visible to anyone using the environment.

## Steps (for the assistant driving the session)
1. **Creds → `.env`.** Ask the user for `IRIS_CNIC` and `IRIS_PASSWORD`, then
   write them to `.env` (gitignored). Never echo them back or log them.
   ```
   IRIS_CNIC=...
   IRIS_PASSWORD=...
   ```
2. **Install Playwright + a browser.** Prefer the cached Chromium (no download):
   ```bash
   pip install -q playwright python-dotenv
   export SPIKE_BROWSER_EXEC=$(ls -d /opt/pw-browsers/chromium-*/chrome-linux/chrome 2>/dev/null | head -1)
   ```
   If `/opt/pw-browsers` has no `chromium-*` dir, run `playwright install chromium`
   instead (needs the Playwright CDN reachable) and unset `SPIKE_BROWSER_EXEC`.
3. **Run it in the background** (so you can hand over the OTP while it polls):
   ```bash
   python scripts/spike_salaried.py --headless --tax-year 2025 --otp-file runs/otp.txt
   ```
4. **OTP handoff.** When it prints *"IRIS is asking for a one-time code … write
   the code into runs/otp.txt"*, ask the user for the code from their phone, then:
   ```bash
   printf '%s' '<code>' > runs/otp.txt
   ```
   The run picks it up and continues. **Never guess the code.**
5. **Result.** It fills the Salary tab + one withholding line + two wealth rows,
   **saves a draft**, and writes:
   - `config/iris_map/salaried.draft.yaml` — the locators that actually worked
   - `docs/spike_notes.md` — per-step log (stable selector vs. needs-fallback)
   - `traces/spike_salaried_<ts>.zip` — open with `playwright show-trace`
6. **Report** which fields used a stable selector and which were flagged for the
   vision fallback. **Do not submit.** If a Submit / Verify / PIN dialog ever
   appears, stop and surface it — that is the human's step.
