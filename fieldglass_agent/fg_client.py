"""Fieldglass API client with OAuth 2.0 client_credentials token caching.

The same discipline as a production integration client:
- fetch a token once, cache it, refresh 60s before expiry;
- send Bearer token AND application key on every call;
- on a 401, invalidate the cached token and retry once (server-side
  token stores get cycled; a client that trusts its cache until local
  expiry locks itself out for the rest of the hour);
- surface HTTP and transport errors as structured results instead of
  raising through the agent (tools should return data the model can
  reason about).
"""

import os
import time

import httpx


class FieldglassClient:
    def __init__(self, http_client: httpx.Client | None = None):
        self.base_url = os.environ.get("FG_BASE_URL", "http://127.0.0.1:8085")
        self.client_id = os.environ.get("FG_CLIENT_ID", "demo-client")
        self.client_secret = os.environ.get("FG_CLIENT_SECRET", "demo-secret")
        self.api_key = os.environ.get("FG_API_KEY", "demo-app-key")
        self._http = http_client or httpx.Client(base_url=self.base_url, timeout=10)
        self._token: str | None = None
        self._token_expiry: float = 0.0

    # -- auth ------------------------------------------------------------
    def invalidate_token(self) -> None:
        self._token = None
        self._token_expiry = 0.0

    def _get_token(self) -> str:
        if self._token and time.time() < self._token_expiry - 60:
            return self._token
        resp = self._http.post(
            "/oauth2/token",
            data={
                "grant_type": "client_credentials",
                "client_id": self.client_id,
                "client_secret": self.client_secret,
            },
        )
        resp.raise_for_status()
        payload = resp.json()
        self._token = payload["access_token"]
        self._token_expiry = time.time() + payload.get("expires_in", 3600)
        return self._token

    def _headers(self) -> dict:
        return {
            "Authorization": f"Bearer {self._get_token()}",
            "X-ApplicationKey": self.api_key,
        }

    # -- request core ----------------------------------------------------
    def _request(self, method: str, path: str, **kwargs) -> dict:
        """One retry on 401 with a fresh token; structured errors otherwise."""
        for attempt in (1, 2):
            try:
                headers = self._headers()
            except httpx.HTTPError as exc:
                return {
                    "error": True,
                    "status_code": None,
                    "detail": f"token acquisition failed: {exc}",
                }
            try:
                resp = self._http.request(method, path, headers=headers, **kwargs)
            except httpx.HTTPError as exc:
                return {
                    "error": True,
                    "status_code": None,
                    "detail": f"transport error: {exc}",
                }
            if resp.status_code == 401 and attempt == 1:
                # Server no longer honors our cached token — refresh and retry.
                self.invalidate_token()
                continue
            if resp.status_code >= 400:
                return {
                    "error": True,
                    "status_code": resp.status_code,
                    "detail": resp.text,
                }
            return resp.json()
        # Unreachable, but keeps type-checkers honest.
        return {"error": True, "status_code": None, "detail": "retry exhausted"}

    # -- api -------------------------------------------------------------
    def list_workers(self, status: str | None = None, name_contains: str | None = None) -> dict:
        params = {}
        if status:
            params["status"] = status
        if name_contains:
            params["name_contains"] = name_contains
        return self._request("GET", "/api/v1/workers", params=params)

    def get_worker(self, worker_id: str) -> dict:
        return self._request("GET", f"/api/v1/workers/{worker_id}")

    def connector_runs(self, connector_id: str) -> dict:
        return self._request("GET", f"/api/v1/connectors/{connector_id}/runs")

    def create_job_posting(self, payload: dict) -> dict:
        return self._request("POST", "/api/v1/job-postings", json=payload)


_client: FieldglassClient | None = None


def get_client() -> FieldglassClient:
    """Module-level singleton so tools share one token cache.
    Tests replace it via set_client()."""
    global _client
    if _client is None:
        _client = FieldglassClient()
    return _client


def set_client(client: FieldglassClient | None) -> None:
    global _client
    _client = client
