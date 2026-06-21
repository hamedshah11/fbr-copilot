"""API: create / status / approve, and the never-submit guarantee."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

import api
from api import app

client = TestClient(app)


@pytest.fixture(autouse=True)
def _clear_jobs():
    api._JOBS.clear()
    yield
    api._JOBS.clear()


def test_healthz():
    assert client.get("/healthz").json() == {"status": "ok"}


def test_create_status_flow(sample_raw):
    resp = client.post("/returns", json={"tax_return": sample_raw})
    assert resp.status_code == 201
    job = resp.json()
    assert job["status"] == "queued"
    assert job["tax_return"]["taxpayer_name"] == "Test Taxpayer"

    got = client.get(f"/returns/{job['id']}")
    assert got.status_code == 200
    assert got.json()["id"] == job["id"]


def test_create_invalid_returns_422():
    resp = client.post("/returns", json={"tax_return": {"tax_year": 2025}})
    assert resp.status_code == 422
    assert "taxpayer_name" in resp.json()["detail"]


def test_get_unknown_job_404():
    assert client.get("/returns/nope").status_code == 404


def test_no_submit_endpoint_exists():
    routes = {r.path for r in app.routes}
    assert not any("submit" in p for p in routes), "there must be no submit endpoint"


def test_approve_only_allowed_when_drafted(sample_raw):
    job = client.post("/returns", json={"tax_return": sample_raw}).json()
    # freshly created job is queued, not drafted -> approval is rejected
    resp = client.post(f"/returns/{job['id']}/approve")
    assert resp.status_code == 409

    # once a draft exists, approval succeeds (and still never submits)
    api._JOBS[job["id"]].status = api.JobStatus.DRAFTED
    ok = client.post(f"/returns/{job['id']}/approve")
    assert ok.status_code == 200
    assert ok.json()["status"] == "approved"
