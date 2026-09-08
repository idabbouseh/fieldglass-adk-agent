"""Seed data for the mock Fieldglass API.

Shapes mirror SAP Fieldglass REST payloads closely enough to be
recognizable to anyone who has worked the real API: workers with
master references and statuses, and connector run history with the
error signatures that actually occur in production integrations.

Deliberately includes "ugly records" — the ones real integrations die on:
multibyte names, apostrophes, a missing end date, and one master
reference shared by two worker records.
"""

WORKERS = [
    {
        "worker_id": "FGW-0001",
        "master_worker_ref": "MW-88001",
        "first_name": "Maria",
        "last_name": "Gonzalez",
        "status": "Active",
        "security_id": "SEC-11001",
        "buyer_ref": "EMP-70431",
        "cost_center": "CC-4100",
        "start_date": "2025-11-03",
        "end_date": "2026-11-02",
    },
    {
        "worker_id": "FGW-0002",
        "master_worker_ref": "MW-88002",
        "first_name": "Zoë",
        "last_name": "Åström",
        "status": "Active",
        "security_id": "SEC-11002",
        "buyer_ref": "EMP-70988",
        "cost_center": "CC-4100",
        "start_date": "2026-01-12",
        "end_date": "2026-12-31",
    },
    {
        "worker_id": "FGW-0003",
        "master_worker_ref": "MW-88003",
        "first_name": "Liam",
        "last_name": "O'Brien",
        "status": "Pending Activation",
        "security_id": "SEC-11003",
        "buyer_ref": None,
        "cost_center": "CC-4200",
        "start_date": "2026-09-15",
        "end_date": "2027-09-14",
    },
    {
        "worker_id": "FGW-0004",
        "master_worker_ref": "MW-88004",
        "first_name": "Priya",
        "last_name": "Natarajan",
        "status": "Active",
        "security_id": "SEC-11004",
        "buyer_ref": "EMP-71230",
        "cost_center": "CC-4300",
        "start_date": "2024-06-01",
        "end_date": None,  # the classic: contractor with no end date
    },
    {
        "worker_id": "FGW-0005",
        "master_worker_ref": "MW-88005",
        "first_name": "Dmitri",
        "last_name": "Volkov",
        "status": "Closed",
        "security_id": "SEC-11005",
        "buyer_ref": "EMP-69544",
        "cost_center": "CC-4100",
        "start_date": "2024-02-19",
        "end_date": "2026-02-18",
    },
    {
        "worker_id": "FGW-0006",
        # Same master ref as FGW-0005: a re-engaged worker. Consolidation
        # logic must pick exactly one record per master or access breaks.
        "master_worker_ref": "MW-88005",
        "first_name": "Dmitri",
        "last_name": "Volkov",
        "status": "Active",
        "security_id": "SEC-11005",
        "buyer_ref": "EMP-69544",
        "cost_center": "CC-4400",
        "start_date": "2026-03-02",
        "end_date": "2027-03-01",
    },
    {
        "worker_id": "FGW-0007",
        "master_worker_ref": "MW-88007",
        "first_name": "Aisha",
        "last_name": "Bello",
        "status": "Active",
        "security_id": "SEC-11007",
        "buyer_ref": "EMP-72100",
        "cost_center": "CC-4200",
        "start_date": "2026-05-05",
        "end_date": "2026-11-05",
    },
    {
        "worker_id": "FGW-0008",
        "master_worker_ref": "MW-88008",
        "first_name": "Jean-Luc",
        "last_name": "Beaumont",
        "status": "Pending Activation",
        "security_id": None,  # missing security id: downstream IAM will reject
        "buyer_ref": "EMP-72455",
        "cost_center": "CC-4300",
        "start_date": "2026-09-22",
        "end_date": "2027-03-21",
    },
]

# Run history for the worker-download connector feeding the customer's
# identity system. The pattern buried in here is the demo's diagnosis
# target: a certificate expired on 09-04, causing an auth failure streak,
# preceded by a suspicious zero-record run after a watermark reset.
CONNECTOR_RUNS = {
    "SAILPOINT_WORKER_DL": [
        {
            "run_id": "R-1041",
            "started_at": "2026-09-08T03:20:00Z",
            "status": "Failed",
            "records_read": 0,
            "records_written": 0,
            "errors": [
                {"code": "AUTH_401", "message": "TLS client certificate expired (thumbprint 7F:AA:..)"}
            ],
        },
        {
            "run_id": "R-1040",
            "started_at": "2026-09-07T03:20:00Z",
            "status": "Failed",
            "records_read": 0,
            "records_written": 0,
            "errors": [
                {"code": "AUTH_401", "message": "TLS client certificate expired (thumbprint 7F:AA:..)"}
            ],
        },
        {
            "run_id": "R-1039",
            "started_at": "2026-09-06T03:20:00Z",
            "status": "Failed",
            "records_read": 0,
            "records_written": 0,
            "errors": [
                {"code": "AUTH_401", "message": "TLS client certificate expired (thumbprint 7F:AA:..)"}
            ],
        },
        {
            "run_id": "R-1038",
            "started_at": "2026-09-05T03:20:00Z",
            "status": "Completed",
            "records_read": 2489,
            "records_written": 2489,
            "errors": [],
        },
        {
            "run_id": "R-1037",
            "started_at": "2026-09-04T03:20:00Z",
            "status": "Completed",
            "records_read": 0,
            "records_written": 0,
            "errors": [],
            "note": "delta watermark reset by admin at 2026-09-03T21:10Z",
        },
        {
            "run_id": "R-1036",
            "started_at": "2026-09-03T03:20:00Z",
            "status": "Completed",
            "records_read": 2493,
            "records_written": 2491,
            "errors": [
                {"code": "REC_REJECT", "message": "2 records rejected: missing security_id"}
            ],
        },
        {
            "run_id": "R-1035",
            "started_at": "2026-09-02T03:20:00Z",
            "status": "Completed",
            "records_read": 2490,
            "records_written": 2490,
            "errors": [],
        },
        {
            "run_id": "R-1034",
            "started_at": "2026-09-01T03:20:00Z",
            "status": "Completed",
            "records_read": 2488,
            "records_written": 2488,
            "errors": [],
        },
    ]
}

JOB_POSTINGS = []  # populated by POST /api/v1/job-postings
