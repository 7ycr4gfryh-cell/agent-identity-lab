"""Agent Identity connector client — drives the on-behalf-of-user consent lifecycle.

This is the OBO analogue of mcp-toolbox's gateway_client.py, but instead of a DIY
token-gateway it talks to Google's managed Agent Identity connector + credential vault
(iamconnectorcredentials.googleapis.com). The app uses this only to ORCHESTRATE consent:

  status_or_consent(uid)  -> ("connected", None) if the user's token is in the vault,
                             else ("consent", auth_url) with a sign-in URL to show.
  finalize(uid, validation_state) -> finishes consent after the browser redirect.

The actual BigQuery data access is done by the deployed agent on Agent Engine using its
own Agent Identity to retrieve this same vaulted token — the app never sees the token.

Auth: the app's own service account token (normal bearer; no mTLS needed here, unlike the
agent's cert-bound retrieve). Requires roles/iamconnectors.user on the app SA.
"""

import os
import threading
import urllib.parse

import google.auth
import google.auth.transport.requests
import requests

# Two services: the credentials service (retrieve/finalize) and the connector mgmt
# service (revoke-authorization). Same connector resource name, different hosts.
ICC_BASE = "https://iamconnectorcredentials.googleapis.com/v1alpha"
ICM_BASE = "https://iamconnectors.googleapis.com/v1alpha"
PROJECT_ID = os.environ.get("GOOGLE_CLOUD_PROJECT", "")
LOCATION = os.environ.get("GOOGLE_CLOUD_LOCATION", "us-central1")
CONNECTOR = os.environ.get(
    "OBO_CONNECTOR",
    f"projects/{PROJECT_ID}/locations/{LOCATION}/connectors/bigquery-3lo",
)
SCOPES = [os.environ.get("OBO_SCOPE", "https://www.googleapis.com/auth/bigquery")]
# Base of this app's own callback route, e.g. https://chainlit-xxx.run.app
APP_BASE_URL = os.environ.get("APP_BASE_URL", "http://localhost:8080").rstrip("/")

# Stash of consent nonces awaiting finalize, keyed by uid (single-instance demo store).
_lock = threading.Lock()
_pending_nonce: dict[str, str] = {}


def _sa_token() -> str:
    creds, _ = google.auth.default(
        scopes=["https://www.googleapis.com/auth/cloud-platform"]
    )
    creds.refresh(google.auth.transport.requests.Request())
    return creds.token


def _continue_uri(uid: str) -> str:
    # The app owns this route; the uid query param lets the callback correlate the redirect
    # back to the right user (Google appends &user_id_validation_state=... to it).
    return f"{APP_BASE_URL}/oauth/callback?uid={urllib.parse.quote(uid)}"


def _retrieve(uid: str) -> dict:
    """Call credentials:retrieve for (connector, uid). Returns the parsed Operation."""
    url = f"{ICC_BASE}/{CONNECTOR}/credentials:retrieve"
    body = {
        "userId": uid,
        "scopes": SCOPES,
        "continueUri": _continue_uri(uid),
    }
    headers = {
        "Authorization": f"Bearer {_sa_token()}",
        "Content-Type": "application/json",
        "x-goog-user-project": PROJECT_ID,
    }
    r = requests.post(url, json=body, headers=headers, timeout=30)
    r.raise_for_status()
    return r.json()


def _dig(obj, keys):
    """Find the first string value under any of `keys` anywhere in a nested dict/list."""
    found = []

    def rec(o):
        if isinstance(o, dict):
            for k, v in o.items():
                if k in keys and isinstance(v, str):
                    found.append(v)
                rec(v)
        elif isinstance(o, list):
            for v in o:
                rec(v)

    rec(obj)
    return found[0] if found else None


def status_or_consent(uid: str) -> tuple[str, str | None]:
    """Return ('connected', None) or ('consent', auth_url)."""
    op = _retrieve(uid)
    # Already consented: the Operation is done and carries a token.
    if op.get("done") and _dig(op.get("response", {}), ("token",)):
        return "connected", None
    auth_uri = _dig(op, ("authorizationUri", "authUri", "auth_uri"))
    nonce = _dig(op, ("consentNonce", "consent_nonce", "nonce"))
    if not auth_uri:
        return "connected", None  # no token and no consent URI — treat as connected/unknown
    if nonce:
        with _lock:
            _pending_nonce[uid] = nonce
    # Force the Google account chooser so the user can't silently reuse a wrong session.
    auth_uri = auth_uri.replace("prompt=consent", "prompt=select_account%20consent")
    return "consent", auth_uri


def finalize(uid: str, validation_state: str) -> tuple[bool, str]:
    """Finish consent after the browser redirect. Returns (ok, detail)."""
    with _lock:
        nonce = _pending_nonce.get(uid)
    url = f"{ICC_BASE}/{CONNECTOR}/credentials:finalize"
    payload = {"userId": uid, "userIdValidationState": validation_state}
    if nonce:
        payload["consentNonce"] = nonce
    headers = {
        "Authorization": f"Bearer {_sa_token()}",
        "Content-Type": "application/json",
        "x-goog-user-project": PROJECT_ID,
    }
    r = requests.post(url, json=payload, headers=headers, timeout=30)
    ok = r.status_code == 200
    if ok:
        with _lock:
            _pending_nonce.pop(uid, None)
    return ok, ("ok" if ok else r.text[:300])


def revoke(uid: str) -> tuple[bool, str]:
    """Revoke this user's authorization for the connector (disconnect). Returns (ok, detail)."""
    url = f"{ICM_BASE}/{CONNECTOR}:revokeAuthorization"
    headers = {
        "Authorization": f"Bearer {_sa_token()}",
        "Content-Type": "application/json",
        "x-goog-user-project": PROJECT_ID,
    }
    r = requests.post(url, json={"userId": uid}, headers=headers, timeout=30)
    ok = r.status_code == 200
    with _lock:
        _pending_nonce.pop(uid, None)
    return ok, ("ok" if ok else r.text[:300])
