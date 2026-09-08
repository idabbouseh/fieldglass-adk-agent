"""Tests for the mock Fieldglass API: auth flow and endpoint behavior."""

import pytest
from fastapi.testclient import TestClient

from mock_fieldglass.app import app


@pytest.fixture()
def client():
    return TestClient(app)


@pytest.fixture()
def auth_headers(client):
    resp = client.post(
        "/oauth2/token",
        data={
            "grant_type": "client_credentials",
            "client_id": "demo-client",
            "client_secret": "demo-secret",
        },
    )
    assert resp.status_code == 200
    token = resp.json()["access_token"]
    return {"Authorization": f"Bearer {token}", "X-ApplicationKey": "demo-app-key"}


def test_token_rejects_bad_credentials(client):
    resp = client.post(
        "/oauth2/token",
        data={
            "grant_type": "client_credentials",
            "client_id": "demo-client",
            "client_secret": "wrong",
        },
    )
    assert resp.status_code == 401


def test_token_rejects_bad_grant_type(client):
    resp = client.post(
        "/oauth2/token",
        data={
            "grant_type": "password",
            "client_id": "demo-client",
            "client_secret": "demo-secret",
        },
    )
    assert resp.status_code == 400


def test_endpoints_require_bearer_token(client):
    resp = client.get("/api/v1/workers", headers={"X-ApplicationKey": "demo-app-key"})
    assert resp.status_code == 401


def test_endpoints_require_application_key(client, auth_headers):
    headers = {"Authorization": auth_headers["Authorization"]}  # no app key
    resp = client.get("/api/v1/workers", headers=headers)
    assert resp.status_code == 401


def test_list_workers_and_status_filter(client, auth_headers):
    resp = client.get("/api/v1/workers", headers=auth_headers)
    assert resp.status_code == 200
    assert resp.json()["total"] == 8

    resp = client.get(
        "/api/v1/workers", params={"status": "Active"}, headers=auth_headers
    )
    body = resp.json()
    assert body["total"] == 5
    assert all(w["status"] == "Active" for w in body["workers"])


def test_name_filter_handles_ugly_records(client, auth_headers):
    resp = client.get(
        "/api/v1/workers", params={"name_contains": "o'brien"}, headers=auth_headers
    )
    assert resp.json()["total"] == 1

    resp = client.get(
        "/api/v1/workers", params={"name_contains": "zoë"}, headers=auth_headers
    )
    assert resp.json()["total"] == 1


def test_get_worker_404(client, auth_headers):
    resp = client.get("/api/v1/workers/FGW-9999", headers=auth_headers)
    assert resp.status_code == 404


def test_connector_runs(client, auth_headers):
    resp = client.get(
        "/api/v1/connectors/SAILPOINT_WORKER_DL/runs", headers=auth_headers
    )
    assert resp.status_code == 200
    assert resp.json()["total"] == 8

    resp = client.get("/api/v1/connectors/NOPE/runs", headers=auth_headers)
    assert resp.status_code == 404


def test_create_job_posting(client, auth_headers):
    resp = client.post(
        "/api/v1/job-postings",
        json={
            "title": "Integration Analyst",
            "description": "Support worker-download feeds",
            "cost_center": "CC-4100",
            "rate_max": 95.0,
        },
        headers=auth_headers,
    )
    assert resp.status_code == 201
    body = resp.json()
    assert body["job_posting_id"].startswith("JP-")
    assert body["status"] == "Draft Submitted"
