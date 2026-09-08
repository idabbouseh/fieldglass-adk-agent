# Deploying Fieldglass Advisor to Agent Engine (Agent Runtime)

Local `adk web` is the demo path. This is the managed path — Vertex AI
Agent Engine, now surfaced as **Agent Runtime** inside the Gemini
Enterprise Agent Platform — and what changes when the mock becomes a
real enterprise system.

## Deploy steps (requires a GCP project with billing)

```bash
gcloud auth login
gcloud config set project <PROJECT_ID>
gcloud services enable aiplatform.googleapis.com

pip install "google-cloud-aiplatform[adk,agent_engines]"

# From the repo root — packages fieldglass_agent and deploys the managed runtime.
adk deploy agent_engine \
  --project <PROJECT_ID> \
  --region us-central1 \
  fieldglass_agent
```

Runtime configuration (env vars like `FG_BASE_URL`, `FG_CLIENT_ID`,
`FG_CLIENT_SECRET`, `FG_API_KEY`, resource sizing) goes in an
`.agent_engine_config.json` in the agent directory, or is passed via
`--agent_engine_config_file`. Older tutorials show `--staging_bucket`
and `--env_file`; both are deprecated in current ADK CLI versions.
For a demo, the mock API can run on Cloud Run so the deployed agent has
something to call.

## Production hardening (what changes against a real tenant)

| Demo shortcut | Production replacement |
|---|---|
| `GOOGLE_API_KEY` in `.env` (AI Studio) | On Agent Runtime there is no API key at all: the runtime authenticates to Vertex AI as its **attached service account** via Application Default Credentials (`GOOGLE_GENAI_USE_VERTEXAI=TRUE`). Workload Identity Federation is the analogous keyless pattern only for workloads running *outside* Google Cloud (CI, on-prem, another cloud) that must call in. |
| Client secret in env | Secret Manager with CMEK; rotation on schedule; per-environment credentials |
| Open egress to the mock | **VPC Service Controls** perimeter around the Google-side resources (Vertex AI, Secret Manager, storage). The Fieldglass API itself is external SaaS and cannot sit inside the perimeter — control that leg with restricted egress, an allowlisted secure web proxy or NAT with firewall rules, and mTLS to the gateway. |
| Any-model default | **Pin the model version.** Flash iterates roughly monthly and old versions retire on schedule (gemini-2.5-flash retires 2026-10-16 — this repo's default moved once already for exactly that reason). Every bump goes through the regression gate below before rollout. |
| Unmonitored agent | Agent observability + audit logging of every tool call; the two-phase write pattern stays — no autonomous writes to systems of record |
| One shared token | Per-tenant credentials; token cache keyed by tenant; certificate/secret expiry tracked with alerting (cert expiry is a silent, scheduled outage — the demo's failure streak is exactly this) |

## Regression gate for model bumps

The seed of the gate lives in this repo: the pytest suite pins the
*behavioral* contract (diagnosis findings, guardrail enforcement,
structured errors) independent of any model. On top of that, capture
golden conversations (prompt → expected tool calls → expected findings
summarized) as ADK evalsets and run `adk eval` against the candidate
model version before switching `FG_AGENT_MODEL`. Treat it exactly like a
connector config change: witnessed before/after in the right
environment, with a rollback value on hand.

## Session and memory

Agent Runtime provides managed Sessions and Memory Bank. For this agent,
session state should hold the confirmation status of pending writes (the
previewed job posting awaiting approval) rather than re-deriving it from
chat history — the in-process `_pending_confirmations` set in `tools.py`
becomes session state there. ADK also offers a native alternative:
`FunctionTool(draft_job_posting, require_confirmation=True)` pushes the
approval to the client UI; the in-code variant is kept because it
survives framework changes and is testable without a model.
