# Deploying Fieldglass Advisor to Agent Engine

Local `adk web` is the demo path. This is the managed path and what
changes when the mock becomes a real enterprise system.

## Deploy steps (requires a GCP project with billing)

```bash
gcloud auth login
gcloud config set project <PROJECT_ID>
gcloud services enable aiplatform.googleapis.com

pip install "google-cloud-aiplatform[adk,agent_engines]"

# From the repo root — packages fieldglass_agent and deploys the managed runtime
adk deploy agent_engine \
  --project <PROJECT_ID> \
  --region us-central1 \
  --staging_bucket gs://<BUCKET> \
  fieldglass_agent
```

Then point the deployed agent at a reachable API base URL via env vars in
the deploy config (`FG_BASE_URL`, `FG_CLIENT_ID`, `FG_CLIENT_SECRET`,
`FG_API_KEY`) — for a demo, the mock can run on Cloud Run.

## Production hardening (what changes against a real tenant)

| Demo shortcut | Production replacement |
|---|---|
| `GOOGLE_API_KEY` in `.env` | **Workload Identity Federation** — no long-lived keys; the runtime's service identity authenticates to Vertex/Gemini |
| Client secret in env | Secret Manager with CMEK; rotation on schedule; per-environment credentials |
| Open egress to the mock | **VPC Service Controls** perimeter around the runtime and the API; Private Service Connect to the enterprise gateway |
| Any-model default | **Pin the model version.** Flash iterates roughly monthly; every bump goes through an eval regression suite before rollout (the same discipline as connector config changes: witnessed before/after in the right environment) |
| Unmonitored agent | Agent observability + audit logging of every tool call; the two-phase write pattern stays — no autonomous writes to systems of record |
| One shared token | Per-tenant credentials; token cache keyed by tenant; certificate/secret expiry tracked with alerting (cert expiry is a silent, scheduled outage — the demo's failure streak is exactly this) |

## Session and memory

Agent Engine provides managed Sessions and Memory Bank. For this agent,
session state should hold the confirmation status of pending writes
(the previewed job posting awaiting approval) rather than re-deriving it
from chat history.
