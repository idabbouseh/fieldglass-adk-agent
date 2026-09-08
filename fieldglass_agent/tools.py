"""Agent tools. Plain functions with type hints and docstrings — ADK
derives the tool schema from these, so the docstrings are the contract
the model sees.

Design rules (the same safety contract used on live enterprise systems):
- read tools return raw facts plus computed findings, never guesses;
- the write tool is two-phase and ENFORCED IN CODE: a confirmed write is
  rejected unless the identical payload was previewed first. (ADK also
  ships a native human-in-the-loop alternative — FunctionTool(...,
  require_confirmation=True) — the in-code variant is used here so the
  guardrail survives even if the agent framework changes.)
"""

import json
import statistics

from .fg_client import get_client

# Payload fingerprints that have been previewed and may be confirmed once.
_pending_confirmations: set[str] = set()


def _payload_key(payload: dict) -> str:
    return json.dumps(payload, sort_keys=True)


def search_workers(status: str = "", name_contains: str = "") -> dict:
    """Search contingent workers in Fieldglass.

    Args:
        status: optional exact status filter, e.g. "Active",
            "Pending Activation", "Closed". Empty means all statuses.
        name_contains: optional case-insensitive substring matched against
            first or last name.

    Returns:
        dict with total count and the matching worker records.
    """
    return get_client().list_workers(status or None, name_contains or None)


def get_worker(worker_id: str) -> dict:
    """Fetch one worker record by its Fieldglass worker id (e.g. "FGW-0004").

    Returns the full worker record, or an error dict with status_code 404
    if the id does not exist.
    """
    return get_client().get_worker(worker_id)


def diagnose_connector_feed(connector_id: str = "SAILPOINT_WORKER_DL") -> dict:
    """Analyze a connector's recent run history and diagnose feed health.

    Applies the standard integration triage model (source -> transform ->
    transport -> target) to the run history: authentication failure
    streaks, recovered outages, zero-record anomalies, record-count drops
    versus baseline, and rejected-record clusters.

    Args:
        connector_id: the connector to analyze. Defaults to the
            SailPoint worker download.

    Returns:
        dict with the raw runs plus computed findings and recommended
        next checks. Facts only — counts and error codes, no speculation.
    """
    payload = get_client().connector_runs(connector_id)
    if payload.get("error"):
        return payload

    runs = payload.get("runs", [])
    if not runs:
        return {
            "connector_id": connector_id,
            "runs_analyzed": 0,
            "findings": [
                "No run history returned. An empty history is a finding, not a "
                "healthy state: the connector may never have executed, its "
                "schedule may be disabled, or history retention purged."
            ],
            "recommended_next_checks": [
                "Confirm the connector schedule is enabled and check "
                "gateway-side execution logs for suppressed runs."
            ],
            "runs": [],
        }

    # Never trust ordering from an API: sort newest-first ourselves.
    runs = sorted(runs, key=lambda r: r.get("started_at", ""), reverse=True)

    findings: list[str] = []
    recommendations: list[str] = []

    # --- failures: current streak AND recovered outages -----------------
    failed = [r for r in runs if r["status"] == "Failed"]
    streak = 0
    for run in runs:  # newest first
        if run["status"] == "Failed":
            streak += 1
        else:
            break
    all_fail_codes = sorted(
        {e["code"] for r in failed for e in r.get("errors", [])}
    )
    if streak:
        streak_codes = sorted(
            {e["code"] for r in runs[:streak] for e in r.get("errors", [])}
        )
        findings.append(
            f"ONGOING OUTAGE: {streak} consecutive failed run(s), most recent "
            f"first; error codes: {streak_codes}"
        )
    older_failures = len(failed) - streak
    if older_failures:
        findings.append(
            f"{older_failures} additional failed run(s) earlier in the window "
            "(recovered outage) — check what changed around the recovery."
        )
    if "AUTH_401" in all_fail_codes:
        recommendations.append(
            "Transport-layer auth failure: check TLS client certificate expiry "
            "and registration on the gateway before touching mappings or data."
        )

    # --- volume baseline and zero-record anomalies ----------------------
    completed = [r for r in runs if r["status"] == "Completed"]
    nonzero = [r for r in completed if r["records_read"] > 0]
    baseline: float | None = None
    if nonzero:
        baseline = statistics.median(r["records_read"] for r in nonzero)
        findings.append(
            f"Baseline records per successful non-empty run (median): {baseline:g}"
        )

    zero_runs = [r for r in completed if r["records_read"] == 0]
    for r in zero_runs:
        note = r.get("note", "no note on run")
        findings.append(
            f"Zero-record completed run {r['run_id']} at {r['started_at']} ({note}) "
            "- a silent-drop signature, not a success."
        )
        recommendations.append(
            f"Treat run {r['run_id']} as an incident: verify the delta watermark "
            "value and reconcile source count vs file count for that window."
        )
    if completed and not nonzero:
        findings.append(
            "Every completed run in the window read 0 records: the feed is "
            "effectively down even though runs report success (classic stuck "
            "watermark or empty-scope filter)."
        )
        recommendations.append(
            "Compare the connector's delta watermark against the source "
            "system's current change volume; run a scoped full extract to "
            "confirm the source still has in-scope records."
        )

    if baseline is not None:
        for r in nonzero:
            if r["records_read"] < baseline * 0.9:
                findings.append(
                    f"Run {r['run_id']} read {r['records_read']} records "
                    f"(>10% below baseline {baseline:g})."
                )

    # --- rejected records, on ANY run (failed runs drop records too) ----
    for r in runs:
        dropped = r.get("records_read", 0) - r.get("records_written", 0)
        if dropped > 0:
            msgs = [e["message"] for e in r.get("errors", [])]
            findings.append(
                f"Run {r['run_id']} ({r['status']}): {dropped} record(s) read "
                f"but not written. Errors: {msgs}"
            )
            recommendations.append(
                "Rejected records are a data-quality signal at the target: list "
                "the failing records and check the field named in the rejection "
                "first."
            )

    if not findings:
        findings.append("No anomalies detected in the available run history.")

    return {
        "connector_id": connector_id,
        "runs_analyzed": len(runs),
        "findings": findings,
        "recommended_next_checks": recommendations,
        "runs": runs,
    }


def draft_job_posting(
    title: str,
    description: str,
    cost_center: str,
    rate_max: float,
    confirmed: bool = False,
) -> dict:
    """Create a job posting in Fieldglass — two-phase, human-confirmed.

    Phase 1 (confirmed=False, the default): returns a preview of exactly
    what would be created and does NOT write anything.
    Phase 2 (confirmed=True): performs the write, but ONLY if the
    identical payload was previewed first — an unpreviewed confirmed call
    is rejected by the tool itself, not just by instruction. Only set
    confirmed=True after the human has explicitly approved the previewed
    draft in the conversation.

    Args:
        title: job posting title.
        description: role description shown to suppliers.
        cost_center: charging cost center, e.g. "CC-4100".
        rate_max: maximum bill rate in USD.
        confirmed: set True ONLY after explicit human approval of the preview.

    Returns:
        Phase 1: {"requires_confirmation": True, "preview": {...}}.
        Phase 2: the created posting record from the API, or a rejection
        if no matching preview exists.
    """
    payload = {
        "title": title,
        "description": description,
        "cost_center": cost_center,
        "rate_max": rate_max,
    }
    key = _payload_key(payload)

    if not confirmed:
        _pending_confirmations.add(key)
        return {
            "requires_confirmation": True,
            "preview": payload,
            "message": (
                "No write performed. Show this preview to the user and ask for "
                "explicit approval before calling again with confirmed=True."
            ),
        }

    if key not in _pending_confirmations:
        return {
            "error": True,
            "requires_confirmation": True,
            "detail": (
                "Rejected: no matching preview for this payload. Call the tool "
                "without confirmed first, show the user the preview, and only "
                "confirm after explicit approval."
            ),
        }

    _pending_confirmations.discard(key)
    return get_client().create_job_posting(payload)
