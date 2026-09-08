"""Mock SAP Fieldglass REST API.

Faithful to the real integration surface in the two ways that matter
for the demo:

1. Auth is OAuth 2.0 client_credentials at POST /oauth2/token, and every
   API call must carry BOTH the Bearer access token and an application
   key header (X-ApplicationKey) — exactly the dual-credential pattern
   the real Fieldglass API gateway enforces.
2. Payload shapes and failure modes mirror production: status filters,
   404s on unknown ids, connector run history with error signatures.

Run:  uvicorn mock_fieldglass.app:app --port 8085
"""

import os
import secrets
import time

from fastapi import Depends, FastAPI, Form, Header, HTTPException
from pydantic import BaseModel

from . import data

CLIENT_ID = os.environ.get("FG_CLIENT_ID", "demo-client")
CLIENT_SECRET = os.environ.get("FG_CLIENT_SECRET", "demo-secret")
API_KEY = os.environ.get("FG_API_KEY", "demo-app-key")
TOKEN_TTL_SECONDS = 3600

app = FastAPI(title="Mock SAP Fieldglass API", version="1.0")

# access_token -> expiry epoch seconds
_tokens: dict[str, float] = {}


@app.post("/oauth2/token")
def issue_token(
    grant_type: str = Form(...),
    client_id: str = Form(...),
    client_secret: str = Form(...),
):
    if grant_type != "client_credentials":
        raise HTTPException(status_code=400, detail="unsupported_grant_type")
    if client_id != CLIENT_ID or client_secret != CLIENT_SECRET:
        raise HTTPException(status_code=401, detail="invalid_client")
    token = secrets.token_urlsafe(24)
    _tokens[token] = time.time() + TOKEN_TTL_SECONDS
    return {
        "access_token": token,
        "token_type": "Bearer",
        "expires_in": TOKEN_TTL_SECONDS,
    }


def require_auth(
    authorization: str | None = Header(default=None),
    x_applicationkey: str | None = Header(default=None),
):
    """Both credentials, always — a Bearer token alone is a 401 on the
    real gateway, and a lone application key is too."""
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="missing bearer token")
    token = authorization.removeprefix("Bearer ").strip()
    expiry = _tokens.get(token)
    if expiry is None or expiry < time.time():
        raise HTTPException(status_code=401, detail="invalid or expired token")
    if x_applicationkey != API_KEY:
        raise HTTPException(status_code=401, detail="missing or invalid application key")


@app.get("/api/v1/workers", dependencies=[Depends(require_auth)])
def list_workers(status: str | None = None, name_contains: str | None = None):
    rows = data.WORKERS
    if status:
        rows = [w for w in rows if w["status"].lower() == status.lower()]
    if name_contains:
        needle = name_contains.lower()
        rows = [
            w
            for w in rows
            if needle in w["first_name"].lower() or needle in w["last_name"].lower()
        ]
    return {"total": len(rows), "workers": rows}


@app.get("/api/v1/workers/{worker_id}", dependencies=[Depends(require_auth)])
def get_worker(worker_id: str):
    for w in data.WORKERS:
        if w["worker_id"] == worker_id:
            return w
    raise HTTPException(status_code=404, detail=f"worker {worker_id} not found")


@app.get(
    "/api/v1/connectors/{connector_id}/runs", dependencies=[Depends(require_auth)]
)
def connector_runs(connector_id: str):
    runs = data.CONNECTOR_RUNS.get(connector_id)
    if runs is None:
        raise HTTPException(status_code=404, detail=f"connector {connector_id} not found")
    return {"connector_id": connector_id, "total": len(runs), "runs": runs}


class JobPostingIn(BaseModel):
    title: str
    description: str
    cost_center: str
    rate_max: float


@app.post(
    "/api/v1/job-postings", dependencies=[Depends(require_auth)], status_code=201
)
def create_job_posting(body: JobPostingIn):
    posting = {
        "job_posting_id": f"JP-{9000 + len(data.JOB_POSTINGS) + 1}",
        "status": "Pending Approval",  # real FG postings enter an approval chain
        **body.model_dump(),
    }
    data.JOB_POSTINGS.append(posting)
    return posting
