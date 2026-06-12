"""Thin client for the deployed agent on Vertex AI Agent Engine.

The agent reasons and runs its tools in the Agent Engine runtime; this app only sends the
user's message and streams text back. `user_id` is the Auth0 sub — the same key the agent's
Agent Identity uses to fetch that user's BigQuery token from the vault.
"""

import json
import os

import google.auth
import google.auth.transport.requests
import requests

PROJECT_ID = os.environ.get("GOOGLE_CLOUD_PROJECT", "")
LOCATION = os.environ.get("GOOGLE_CLOUD_LOCATION", "us-central1")
ENGINE_ID = os.environ.get("AGENT_ENGINE_ID", "")

BASE = f"https://{LOCATION}-aiplatform.googleapis.com/v1"
RES = f"projects/{PROJECT_ID}/locations/{LOCATION}/reasoningEngines/{ENGINE_ID}"


def _token() -> str:
    creds, _ = google.auth.default(
        scopes=["https://www.googleapis.com/auth/cloud-platform"]
    )
    creds.refresh(google.auth.transport.requests.Request())
    return creds.token


def _headers() -> dict:
    return {"Authorization": f"Bearer {_token()}", "Content-Type": "application/json"}


def create_session(user_id: str) -> str:
    body = {"class_method": "create_session", "input": {"user_id": user_id}}
    r = requests.post(f"{BASE}/{RES}:query", headers=_headers(), json=body, timeout=60)
    r.raise_for_status()
    return r.json()["output"]["id"]


def stream_text(user_id: str, session_id: str, message: str):
    """Yield assistant text chunks from the deployed agent."""
    body = {
        "class_method": "stream_query",
        "input": {"user_id": user_id, "session_id": session_id, "message": message},
    }
    r = requests.post(
        f"{BASE}/{RES}:streamQuery?alt=sse",
        headers=_headers(),
        json=body,
        stream=True,
        timeout=300,
    )
    r.raise_for_status()
    for line in r.iter_lines():
        if not line:
            continue
        s = line.decode("utf-8").strip()
        if s.startswith("data: "):
            s = s[6:]
        if s in ("", "[DONE]"):
            continue
        try:
            event = json.loads(s)
        except json.JSONDecodeError:
            continue
        for part in (event.get("content", {}) or {}).get("parts", []) or []:
            if part.get("text"):
                yield part["text"]
