# Fieldglass Advisor — an ADK agent against an enterprise-shaped API

[![tests](https://github.com/idabbouseh/fieldglass-adk-agent/actions/workflows/tests.yml/badge.svg)](https://github.com/idabbouseh/fieldglass-adk-agent/actions/workflows/tests.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)
[![Python 3.10+](https://img.shields.io/badge/python-3.10%2B-blue.svg)](https://www.python.org/downloads/)

A working Google **Agent Development Kit (ADK)** agent that operates a
mock **SAP Fieldglass** vendor-management API the way a production
integration does: OAuth 2.0 client_credentials with token caching and
401-invalidation retry, a dual-credential gateway (Bearer token **and**
application key on every call), realistic worker data with the ugly
records integrations actually break on, and a connector run history
containing a real-world failure pattern for the agent to diagnose.

Built by a 14-year SAP Fieldglass integration lead as a portfolio
demonstration: the agent encodes the same operating contract I use when
running AI agents against live Fortune 500 tenants — read-only by
default, verify with counts, two-phase human-confirmed writes (enforced
in code, not just prompt), and source → transform → transport → target
triage.

## What the agent can do

| Tool | What it demonstrates |
|---|---|
| `search_workers` / `get_worker` | Grounded enterprise data access through OAuth; structured 404/error handling, no hallucinated records |
| `diagnose_connector_feed` | The showpiece: analyzes run history and finds a 3-run certificate-expiry outage, a silent zero-record run after a watermark reset, recovered outages, and rejected-record clusters — with layer-ordered next checks. Handles the pathological histories too: empty history and all-zero "successful" runs are findings, not health |
| `draft_job_posting` | Two-phase write guardrail enforced in the tool itself: a confirmed write without a matching prior preview is rejected, and each preview authorizes exactly one write |

## Demo transcript (abridged)

> **You:** How healthy is the SailPoint worker feed?
>
> **Agent:** The feed is in an ongoing outage — 3 consecutive failed runs
> (newest first), all `AUTH_401`: the TLS client certificate expired.
> That's transport-layer, so fix certificate registration before touching
> mappings. Two more facts from the history: run R-1037 completed with
> **0 records** right after an admin watermark reset — a silent-drop
> signature, not a success — and run R-1036 read 2,493 but wrote 2,491
> (2 records rejected for missing security_id). Baseline is ~2,490
> records per healthy run. My hypothesis is a scheduled cert expiry
> plus an unrelated watermark incident; cheapest confirmation is the
> gateway's certificate thumbprint and expiry date.

## Run it locally

Python 3.10+ required.

**Windows (PowerShell):**

```powershell
py -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
Copy-Item .env.example .env    # then add your GOOGLE_API_KEY (free at aistudio.google.com)

# terminal 1 — the mock Fieldglass API
uvicorn mock_fieldglass.app:app --port 8085

# terminal 2 — the agent dev UI
adk web fieldglass_agent
# open the printed URL — the agent is "fieldglass_agent"
```

**macOS / Linux:**

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env

uvicorn mock_fieldglass.app:app --port 8085   # terminal 1
adk web fieldglass_agent                       # terminal 2
```

No key yet? Everything except the LLM still works:

```bash
pytest -q        # auth flow, endpoints, diagnosis edge cases, guardrail enforcement
```

## Architecture

```
┌────────────┐   tool calls    ┌──────────────────┐   OAuth2 + app-key   ┌───────────────────┐
│  Gemini     │ ─────────────► │ fieldglass_agent  │ ───────────────────► │ mock_fieldglass    │
│ (via ADK)   │ ◄───────────── │ tools + fg_client │ ◄─────────────────── │ FastAPI, seed data │
└────────────┘   findings      └──────────────────┘   JSON               └───────────────────┘
```

- `mock_fieldglass/` — FastAPI app: `POST /oauth2/token`, workers, connector
  runs, job postings. Enforces Bearer **and** `X-ApplicationKey` on every
  call, echoing the dual-credential pattern of the real Fieldglass
  gateway (whose actual token path is `/api/oauth2/v2.0/token`; the mock
  simplifies the path, not the discipline).
- `fieldglass_agent/fg_client.py` — token cache (refreshes 60s early,
  invalidates and retries once on 401), dual-credential headers,
  structured error returns for HTTP and transport failures.
- `fieldglass_agent/tools.py` — tool functions; docstrings are the schema
  the model sees. The write tool's confirmation gate lives here, in code.
- `fieldglass_agent/agent.py` — the `root_agent` with the operating
  contract as its instruction; model pinned via `FG_AGENT_MODEL`.

## Deploying to Agent Engine / Agent Runtime

See [deploy/agent_engine_notes.md](deploy/agent_engine_notes.md) for the
managed-runtime deploy path and production hardening: attached-service-
account auth via ADC instead of API keys (Workload Identity Federation
only for workloads outside Google Cloud), VPC Service Controls with an
honest treatment of the external-SaaS leg, CMEK, and model-version
pinning with an eval regression gate.

## Why the mock is shaped like this

Every quirk is a production scar, on purpose:

- **Dual credentials** — the real Fieldglass gateway wants both an OAuth
  bearer token and an application key; agents that only handle one fail
  on first contact.
- **Two workers sharing one master reference** — re-engaged workers; the
  consolidation problem behind real identity-feed outages.
- **A completed run with zero records** — the silent-drop signature.
  Dashboards call it green; downstream systems lose access.
- **Names like Zoë, Åström, O'Brien; a missing end date; a missing
  security id** — clean records pass everywhere; integrations die on the
  ugly ones.
