"""Agent tools. Plain functions with type hints and docstrings — ADK
derives the tool schema from these, so the docstrings are the contract
the model sees.

Design rules (the same safety contract used on live enterprise systems):
- read tools return raw facts plus computed findings, never guesses;
- the single write tool is two-phase: it returns a preview until it is
  called with confirmed=True, and the agent's instruction forbids
  setting confirmed=True unless the human explicitly approved.
"""

from .fg_client import get_client


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
    streaks, zero-record anomalies, record-count drops versus baseline,
    and rejected-record clusters.

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
    findings: list[str] = []
    recommendations: list[str] = []

    # Failure streak from most recent run backwards.
    streak = 0
    for run in runs:  # newest first
        if run["status"] == "Failed":
            streak += 1
        else:
            break
    if streak:
        codes = {e["code"] for r in runs[:streak] for e in r.get("errors", [])}
        findings.append(
            f"{streak} consecutive failed run(s), most recent first; error codes: {sorted(codes)}"
        )
        if "AUTH_401" in codes:
            recommendations.append(
                "Transport-layer auth failure: check TLS client certificate expiry "
                "and registration on the gateway before touching mappings or data."
            )

    # Baseline vs anomalies on completed runs.
    completed = [r for r in runs if r["status"] == "Completed"]
    nonzero = [r for r in completed if r["records_read"] > 0]
    if nonzero:
        baseline = sorted(r["records_read"] for r in nonzero)[len(nonzero) // 2]
        findings.append(f"Baseline records per successful run (median): {baseline}")
        for r in completed:
            if r["records_read"] == 0:
                note = r.get("note", "no note on run")
                findings.append(
                    f"Zero-record completed run {r['run_id']} at {r['started_at']} ({note}) "
                    "- a silent-drop signature, not a success."
                )
                recommendations.append(
                    f"Treat run {r['run_id']} as an incident: verify the delta watermark "
                    "value and reconcile source count vs file count for that window."
                )
            elif r["records_read"] < baseline * 0.9:
                findings.append(
                    f"Run {r['run_id']} read {r['records_read']} records "
                    f"(>10% below baseline {baseline})."
                )

    # Rejected-record clusters.
    for r in completed:
        dropped = r["records_read"] - r["records_written"]
        if dropped > 0:
            msgs = [e["message"] for e in r.get("errors", [])]
            findings.append(
                f"Run {r['run_id']}: {dropped} record(s) read but not written. Errors: {msgs}"
            )
            recommendations.append(
                "Rejected records are a data-quality signal at the target: list the "
                "failing records and check the field named in the rejection first."
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
    Phase 2 (confirmed=True): performs the write. Only set confirmed=True
    after the human has explicitly approved the previewed draft in the
    conversation.

    Args:
        title: job posting title.
        description: role description shown to suppliers.
        cost_center: charging cost center, e.g. "CC-4100".
        rate_max: maximum bill rate in USD.
        confirmed: set True ONLY after explicit human approval of the preview.

    Returns:
        Phase 1: {"requires_confirmation": True, "preview": {...}}.
        Phase 2: the created posting record from the API.
    """
    payload = {
        "title": title,
        "description": description,
        "cost_center": cost_center,
        "rate_max": rate_max,
    }
    if not confirmed:
        return {
            "requires_confirmation": True,
            "preview": payload,
            "message": (
                "No write performed. Show this preview to the user and ask for "
                "explicit approval before calling again with confirmed=True."
            ),
        }
    return get_client().create_job_posting(payload)
