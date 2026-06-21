# Lovable UI brief

> **Out of scope until phase 3+** (see `CLAUDE.md`). Placeholder so the intended
> shape of the review UI is captured; do not build yet.

The UI is a **human review + approve** surface over the job API — it never
submits to IRIS.

- **Create**: submit structured tax data (or upload documents) → a drafting job.
- **Review**: show the saved IRIS draft with a **per-field diff** (canonical
  value vs. what was drafted), masked PII, screenshots, and any `needs_human`
  fields surfaced for attention.
- **Approve**: mark a draft as human-reviewed. Approval is **not** submission —
  the final PIN/OTP step happens by a human directly on IRIS.

API today: `POST /returns`, `GET /returns/{id}`, `POST /returns/{id}/approve`.
