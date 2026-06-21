"""FastAPI job API: create / status / approve.

``approve != submit``. Approval marks a *drafted* return as human-reviewed.
The final PIN / OTP submission on IRIS is always performed by a human, never by
this API — there is no submit endpoint, by design (CLAUDE.md hard rule #1).

The job store here is in-memory. The durable design is a Supabase queue that a
worker claims and writes results back to; that wiring is a later step.
"""

from __future__ import annotations

import uuid
from enum import Enum
from typing import Any

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

from normalize import NormalizationError, normalize
from schema import TaxReturn


class JobStatus(str, Enum):
    QUEUED = "queued"  # accepted, awaiting the worker
    RUNNING = "running"  # worker is drafting on IRIS
    DRAFTED = "drafted"  # draft saved on IRIS, awaiting human review
    NEEDS_HUMAN = "needs_human"  # some fields could not be drafted
    APPROVED = "approved"  # human reviewed; ready for human to submit on IRIS
    ERROR = "error"


class FieldDiff(BaseModel):
    """One line of the per-field review diff."""

    field: str
    drafted: Any | None = None
    status: str = "ok"
    note: str | None = None


class Job(BaseModel):
    id: str
    status: JobStatus = JobStatus.QUEUED
    tax_return: TaxReturn | None = None
    diff: list[FieldDiff] = Field(default_factory=list)
    needs_human: list[str] = Field(default_factory=list)
    error: str | None = None


class CreateJobRequest(BaseModel):
    # Raw return data; normalized + validated server-side so callers get
    # field-level errors rather than guessing at the schema.
    tax_return: dict[str, Any]


# In-memory store — replace with the Supabase job queue.
_JOBS: dict[str, Job] = {}

app = FastAPI(
    title="FBR IRIS Return-Drafting Agent",
    version="0.1.0",
    description="Drafts and saves income-tax returns on IRIS. Never submits.",
)


@app.get("/healthz")
def healthz() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/returns", response_model=Job, status_code=201)
def create_return(req: CreateJobRequest) -> Job:
    """Validate input and enqueue a drafting job."""
    try:
        tax_return = normalize(req.tax_return)
    except NormalizationError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    job = Job(id=uuid.uuid4().hex, status=JobStatus.QUEUED, tax_return=tax_return)
    _JOBS[job.id] = job
    # TODO: enqueue on the Supabase queue for the worker to claim.
    return job


@app.get("/returns/{job_id}", response_model=Job)
def get_return(job_id: str) -> Job:
    """Status + per-field diff for human review."""
    job = _JOBS.get(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="job not found")
    return job


@app.post("/returns/{job_id}/approve", response_model=Job)
def approve_return(job_id: str) -> Job:
    """Mark a drafted return as human-reviewed.

    This records approval only. It does NOT submit the return — filing is a
    human action on IRIS (entering the PIN / OTP).
    """
    job = _JOBS.get(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="job not found")
    if job.status != JobStatus.DRAFTED:
        raise HTTPException(
            status_code=409,
            detail=f"can only approve a drafted return (status={job.status.value})",
        )
    job.status = JobStatus.APPROVED
    return job
