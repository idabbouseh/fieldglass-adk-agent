"""Tests for agent tools, run against the in-process mock API (no network,
no LLM). Verifies the diagnosis logic — including the edge histories that
matter in production — the token-cache recovery path, and the enforced
two-phase write guardrail."""

import pytest
from fastapi.testclient import TestClient

from fieldglass_agent import fg_client, tools
from mock_fieldglass import data
from mock_fieldglass.app import app
from mock_fieldglass import app as mock_app


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


# --- read tools ---------------------------------------------------------


def test_search_workers_status_filter():
    result = tools.search_workers(status="Pending Activation")
    assert result["total"] == 2


def test_search_workers_name_filter_ugly_records():
    assert tools.search_workers(name_contains="o'brien")["total"] == 1
    assert tools.search_workers(name_contains="åström")["total"] == 1


def test_get_worker_not_found_is_structured_error():
    result = tools.get_worker("FGW-9999")
    assert result["error"] is True
    assert result["status_code"] == 404


# --- diagnosis: seeded history ------------------------------------------


def test_diagnose_detects_auth_failure_streak():
    result = tools.diagnose_connector_feed("SAILPOINT_WORKER_DL")
    assert result["runs_analyzed"] == 8
    joined = " ".join(result["findings"])
    assert "ONGOING OUTAGE: 3 consecutive failed run(s)" in joined
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


# --- diagnosis: edge histories ------------------------------------------


@pytest.fixture()
def synthetic_runs(monkeypatch):
    """Swap in a synthetic run history for the test's duration."""

    def _install(runs):
        monkeypatch.setitem(data.CONNECTOR_RUNS, "SYNTH", runs)
        return "SYNTH"

    return _install


def test_diagnose_empty_history_is_a_finding(synthetic_runs):
    cid = synthetic_runs([])
    result = tools.diagnose_connector_feed(cid)
    assert result["runs_analyzed"] == 0
    assert "No run history" in result["findings"][0]
    assert result["recommended_next_checks"]  # never empty-handed


def test_diagnose_all_zero_runs_is_not_healthy(synthetic_runs):
    cid = synthetic_runs(
        [
            {
                "run_id": f"Z-{i}",
                "started_at": f"2026-09-0{i}T03:20:00Z",
                "status": "Completed",
                "records_read": 0,
                "records_written": 0,
                "errors": [],
            }
            for i in range(1, 6)
        ]
    )
    result = tools.diagnose_connector_feed(cid)
    joined = " ".join(result["findings"])
    assert "effectively down" in joined
    assert "No anomalies" not in joined


def test_diagnose_surfaces_recovered_outage(synthetic_runs):
    cid = synthetic_runs(
        [
            {
                "run_id": "N-3",
                "started_at": "2026-09-03T03:20:00Z",
                "status": "Completed",
                "records_read": 100,
                "records_written": 100,
                "errors": [],
            },
            {
                "run_id": "N-2",
                "started_at": "2026-09-02T03:20:00Z",
                "status": "Failed",
                "records_read": 0,
                "records_written": 0,
                "errors": [{"code": "AUTH_401", "message": "cert expired"}],
            },
            {
                "run_id": "N-1",
                "started_at": "2026-09-01T03:20:00Z",
                "status": "Failed",
                "records_read": 0,
                "records_written": 0,
                "errors": [{"code": "AUTH_401", "message": "cert expired"}],
            },
        ]
    )
    result = tools.diagnose_connector_feed(cid)
    joined = " ".join(result["findings"])
    assert "recovered outage" in joined
    assert "2 additional failed run(s)" in joined
    # transport-layer recommendation fires even though the outage recovered
    assert "certificate" in " ".join(result["recommended_next_checks"]).lower()


def test_diagnose_counts_drops_on_failed_runs(synthetic_runs):
    cid = synthetic_runs(
        [
            {
                "run_id": "F-1",
                "started_at": "2026-09-01T03:20:00Z",
                "status": "Failed",
                "records_read": 100,
                "records_written": 40,
                "errors": [{"code": "TARGET_TIMEOUT", "message": "IAM import aborted"}],
            }
        ]
    )
    result = tools.diagnose_connector_feed(cid)
    joined = " ".join(result["findings"])
    assert "60 record(s) read but not written" in joined


# --- token cache recovery -----------------------------------------------


def test_client_recovers_after_server_side_token_cycle():
    # Prime the cache with a valid token.
    assert tools.search_workers()["total"] == 8
    # Simulate the mock restarting (server-side token store wiped).
    mock_app._tokens.clear()
    # The cached token is now invalid server-side; the client must
    # invalidate on 401 and retry with a fresh token transparently.
    result = tools.search_workers()
    assert result.get("error") is not True
    assert result["total"] == 8


# --- two-phase write guardrail ------------------------------------------


def test_draft_job_posting_preview_writes_nothing():
    before = len(data.JOB_POSTINGS)
    result = tools.draft_job_posting(
        title="Data Analyst",
        description="Contingent analyst role",
        cost_center="CC-4200",
        rate_max=80.0,
    )
    assert result["requires_confirmation"] is True
    assert result["preview"]["title"] == "Data Analyst"
    assert len(data.JOB_POSTINGS) == before  # nothing written


def test_confirmed_write_without_preview_is_rejected():
    before = len(data.JOB_POSTINGS)
    result = tools.draft_job_posting(
        title="Sneaky Posting",
        description="never previewed",
        cost_center="CC-4100",
        rate_max=50.0,
        confirmed=True,
    )
    assert result["error"] is True
    assert "no matching preview" in result["detail"].lower()
    assert len(data.JOB_POSTINGS) == before


def test_preview_then_confirm_writes_once():
    tools.draft_job_posting(
        title="Data Analyst",
        description="Contingent analyst role",
        cost_center="CC-4200",
        rate_max=80.0,
    )
    result = tools.draft_job_posting(
        title="Data Analyst",
        description="Contingent analyst role",
        cost_center="CC-4200",
        rate_max=80.0,
        confirmed=True,
    )
    assert result["status"] == "Pending Approval"
    assert result["job_posting_id"].startswith("JP-")
    # The preview token is consumed: a second confirmed call is rejected.
    again = tools.draft_job_posting(
        title="Data Analyst",
        description="Contingent analyst role",
        cost_center="CC-4200",
        rate_max=80.0,
        confirmed=True,
    )
    assert again["error"] is True
