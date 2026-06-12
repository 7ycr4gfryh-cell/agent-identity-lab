"""
=============================================================================
OBO 3LO consent callback service (the `continue_uri`)
=============================================================================
Hosts the post-consent redirect target for the Agent Identity 3-legged OAuth
(on-behalf-of-user) flow used by the customer service agent.

Flow:
  1. The test client drives the agent, which emits an `adk_request_credential`
     carrying an `auth_uri` + `consent_nonce` for a given `user_id`.
  2. The test client POSTs {user_id, consent_nonce} to /prime (out-of-band,
     because the Google-hosted redirect to this service does NOT carry them).
  3. The human opens `auth_uri`, signs in, and consents. Google redirects to the
     connector's Google-hosted oauthcallback, which redirects the browser here
     to /validateUserId?...&user_id_validation_state=<opaque state>.
  4. /validateUserId calls the iamconnectorcredentials FinalizeCredentials API
     with {userId, consentNonce, userIdValidationState}, populating the
     Google-managed credential vault for that user_id.
  5. The test client resumes the agent; the agent re-runs retrieveCredentials,
     now finds the consented token, and calls BigQuery AS THE USER.

This is a single-flight demo service: it keeps the last primed request in memory
and must run as a single Cloud Run instance (min=max=1).
=============================================================================
"""

import os
import threading

import google.auth
import google.auth.transport.requests
import requests
from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, JSONResponse, PlainTextResponse

ICC_BASE = "https://iamconnectorcredentials.googleapis.com/v1alpha"
PROJECT_ID = os.environ.get("GOOGLE_CLOUD_PROJECT", "")

app = FastAPI()

# Single-flight store of the in-progress consent (run with one instance only).
_lock = threading.Lock()
_pending: dict = {}


def _access_token() -> str:
    creds, _ = google.auth.default(
        scopes=["https://www.googleapis.com/auth/cloud-platform"]
    )
    creds.refresh(google.auth.transport.requests.Request())
    return creds.token


@app.get("/healthz")
def healthz() -> PlainTextResponse:
    return PlainTextResponse("ok")


@app.get("/")
def root() -> PlainTextResponse:
    return PlainTextResponse("OBO 3LO callback service. See /validateUserId.")


@app.post("/prime")
async def prime(request: Request) -> JSONResponse:
    """Store the user_id + consent_nonce for the consent about to happen."""
    body = await request.json()
    user_id = body.get("user_id")
    consent_nonce = body.get("consent_nonce")
    connector = body.get("connector", "")
    if not user_id or not consent_nonce:
        return JSONResponse(
            {"error": "user_id and consent_nonce are required"}, status_code=400
        )
    with _lock:
        _pending.clear()
        _pending.update(
            user_id=user_id, consent_nonce=consent_nonce, connector=connector
        )
    return JSONResponse({"primed": True, "user_id": user_id})


@app.get("/validateUserId")
async def validate_user(request: Request) -> HTMLResponse:
    """Receive the post-consent redirect and finalize the credential."""
    qp = dict(request.query_params)
    validation_state = qp.get("user_id_validation_state")
    auth_provider_name = qp.get("auth_provider_name")  # full connector resource

    with _lock:
        pending = dict(_pending)

    if not validation_state:
        return HTMLResponse(
            _page("Missing user_id_validation_state in redirect.", qp), status_code=400
        )
    if not pending:
        return HTMLResponse(
            _page("No primed consent found. Call /prime first.", qp), status_code=409
        )

    connector = auth_provider_name or pending.get("connector")
    url = f"{ICC_BASE}/{connector}/credentials:finalize"
    payload = {
        "userId": pending["user_id"],
        "consentNonce": pending["consent_nonce"],
        "userIdValidationState": validation_state,
    }
    headers = {
        "Authorization": f"Bearer {_access_token()}",
        "Content-Type": "application/json",
    }
    if PROJECT_ID:
        headers["x-goog-user-project"] = PROJECT_ID

    resp = requests.post(url, json=payload, headers=headers, timeout=30)
    ok = resp.status_code == 200
    detail = "Credential finalized." if ok else f"Finalize failed: {resp.text[:300]}"
    with _lock:
        _pending["last_result"] = {"status": resp.status_code, "ok": ok}
    return HTMLResponse(_page(detail, {"finalize_status": resp.status_code}), status_code=(200 if ok else 502))


@app.get("/status")
def status() -> JSONResponse:
    with _lock:
        return JSONResponse(dict(_pending))


def _page(message: str, extra: dict) -> str:
    rows = "".join(f"<li>{k}: {v}</li>" for k, v in extra.items())
    return f"""<!doctype html><html><body style="font-family:sans-serif">
<h3>{message}</h3>
<ul>{rows}</ul>
<p>You can close this window and return to the terminal.</p>
<script>setTimeout(function(){{window.close();}}, 1500);</script>
</body></html>"""
