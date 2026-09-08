"""Tests for agent tools, run against the in-process mock API (no network,
no LLM). Verifies the diagnosis logic and the two-phase write guardrail."""

import pytest
from fastapi.testclient import TestClient

from fieldglass_agent import fg_client, tools
from mock_fieldglass.app import app


@pytest.fixture(autouse=True)
def wired_client():
    """Point the tools' shared client at the in-process app.

    TestClient subclasses httpx.Client, so it drops straight into
    FieldglassClient as the injected http client — no network, no LLM.
    """
    http = TestClient(app)
    fg_client.set_client(fg_client.FieldglassClient(http_client=http))
    yield
    fg_client.set_client(None)


def test_search_workers_status_filter():
    result = tools.search_workers(status="Pending Activation")
    assert result["total"] == 2


def test_get_worker_not_found_is_structured_error():
    result = tools.get_worker("FGW-9999")
    assert result["error"] is True
    assert result["status_code"] == 404


def test_diagnose_detects_auth_failure_streak():
    result = tools.diagnose_connector_feed("SAILPOINT_WORKER_DL")
    assert result["runs_analyzed"] == 8
    joined = " ".join(result["findings"])
    assert "3 consecutive failed run(s)" in joined
    assert "AUTH_401" in joined
    recs = " ".join(result["recommended_next_checks"])
    assert "certificate" in recs.lower()


def test_diagnose_flags_zero_record_run_and_rejects():
    result = tools.diagnose_connector_feed("SAILPOINT_WORKER_DL")
    joined = " ".join(result["findings"])
    assert "Zero-record completed run R-1037" in joined
    assert "2 record(s) read but not written" in joined


def test_diagnose_unknown_connector_returns_error():
    result = tools.diagnose_connector_feed("NOPE")
    assert result["error"] is True
    assert result["status_code"] == 404


def test_draft_job_posting_requires_confirmation():
    result = tools.draft_job_posting(
        title="Data Analyst",
        description="Contingent analyst role",
        cost_center="CC-4200",
        rate_max=80.0,
    )
    assert result["requires_confirmation"] is True
    assert result["preview"]["title"] == "Data Analyst"


def test_draft_job_posting_confirmed_writes():
    result = tools.draft_job_posting(
        title="Data Analyst",
        description="Contingent analyst role",
        cost_center="CC-4200",
        rate_max=80.0,
        confirmed=True,
    )
    assert result["status"] == "Draft Submitted"
    assert result["job_posting_id"].startswith("JP-")
