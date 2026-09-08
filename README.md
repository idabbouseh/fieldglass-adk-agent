# Fieldglass Advisor — an ADK agent against an enterprise-shaped API

A working Google **Agent Development Kit (ADK)** agent that operates a
mock **SAP Fieldglass** vendor-management API the way a production
integration does: OAuth 2.0 client_credentials with token caching, a
dual-credential gateway (Bearer token **and** application key on every
call), realistic worker data with the ugly records integrations actually
break on, and a connector run history containing a real-world failure
pattern for the agent to diagnose.

Built by a 14-year SAP Fieldglass integration lead as a portfolio
demonstration: the agent encodes the same operating contract I use when
running AI agents against live Fortune 500 tenants — read-only by
default, verify with counts, two-phase human-confirmed writes, and
source → transform → transport → target triage.

## What the agent can do

| Tool | What it demonstrates |
|---|---|
| `search_workers` / `get_worker` | Grounded enterprise data access through OAuth; structured 404/error handling, no hallucinated records |
| `diagnose_connector_feed` | The showpiece: analyzes run history and finds a 3-run certificate-expiry failure streak, a silent zero-record run after a watermark reset, and rejected-record clusters — with layer-ordered next checks |
| `draft_job_posting` | Two-phase write guardrail: preview first, writes only after explicit human confirmation (`confirmed=True` is forbidden without it) |

Try: *"How healthy is the SailPoint worker feed?"* then
*"Post a job for an integration analyst in CC-4100 at $95/hr max."*

## Run it locally

```bash
python -m venv .venv && .venv/Scripts/activate   # Windows; use bin/activate elsewhere
pip install -r requirements.txt
cp .env.example .env                              # add your GOOGLE_API_KEY (free at aistudio.google.com)

# terminal 1 — the mock Fieldglass API
uvicorn mock_fieldglass.app:app --port 8085

# terminal 2 — the agent dev UI
adk web
# open the printed URL, pick "fieldglass_advisor"
```

No key yet? Everything except the LLM still works:

```bash
pytest -q        # 16 tests: auth flow, endpoints, diagnosis logic, write guardrail
```

## Architecture

```
┌────────────┐   tool calls    ┌──────────────────┐   OAuth2 + app-key   ┌───────────────────┐
│  Gemini     │ ─────────────► │ fieldglass_agent  │ ───────────────────► │ mock_fieldglass    │
│ (via ADK)   │ ◄───────────── │ tools + fg_client │ ◄─────────────────── │ FastAPI, seed data │
└────────────┘   findings      └──────────────────┘   JSON               └───────────────────┘
```

- `mock_fieldglass/` — FastAPI app: `POST /oauth2/token`, workers, connector
  runs, job postings. Enforces Bearer **and** `X-ApplicationKey`, like the
  real Fieldglass gateway.
- `fieldglass_agent/fg_client.py` — token cache (refreshes 60s early),
  dual-credential headers, structured error returns.
- `fieldglass_agent/tools.py` — tool functions; docstrings are the schema
  the model sees.
- `fieldglass_agent/agent.py` — the `root_agent` with the operating
  contract as its instruction.

## Deploying to Agent Engine

See [deploy/agent_engine_notes.md](deploy/agent_engine_notes.md) for the
managed-runtime deploy path and the production hardening notes
(Workload Identity Federation instead of API keys, VPC Service Controls,
CMEK, model-version pinning with eval regression).

## Why the mock is shaped like this

Every quirk is a production scar, on purpose:

- **Dual credentials** — Fieldglass really does require both an OAuth
  bearer token and an application key; agents that only handle one fail
  on first contact.
- **Two workers sharing one master reference** — re-engaged workers; the
  consolidation problem behind real identity-feed outages.
- **A completed run with zero records** — the silent-drop signature.
  Dashboards call it green; downstream systems lose access.
- **Names like Zoë, Åström, O'Brien; a missing end date; a missing
  security id** — clean records pass everywhere; integrations die on the
  ugly ones.
