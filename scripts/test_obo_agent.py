#!/usr/bin/env python3
"""
=============================================================================
On-behalf-of-user (3LO) consent driver + verification
=============================================================================
Drives the 3-legged OAuth consent round-trip against the DEPLOYED agent and
verifies that BigQuery access follows the consenting human.

Because consent needs a real human at a browser, this runs in two phases:

  initiate <user_id>   ask the agent "what data can I read?", capture the
                       `adk_request_credential` it emits, prime the Cloud Run
                       callback, and print the consent URL to open.
  resume   <user_id>   after the human has consented in the browser, resume the
                       same session so the agent retrieves the user's delegated
                       token and reads BigQuery as them.

State between phases is saved to /tmp/obo_<user_id>.json.

Env: GOOGLE_CLOUD_PROJECT, GOOGLE_CLOUD_LOCATION, AGENT_ENGINE_ID,
     OBO_CONTINUE_URI (Cloud Run /validateUserId base, used for /prime),
     OBO_CONNECTOR (connector resource).
=============================================================================
"""

import json
import os
import sys

import requests
from google.auth import default
from google.auth.transport.requests import Request

PROJECT_ID = os.environ.get("GOOGLE_CLOUD_PROJECT") or os.environ.get("PROJECT_ID")
LOCATION = os.environ.get("GOOGLE_CLOUD_LOCATION", "us-central1")
ENGINE_ID = os.environ.get("AGENT_ENGINE_ID")
CONTINUE_URI = os.environ.get("OBO_CONTINUE_URI", "")  # https://.../validateUserId
CONNECTOR = os.environ.get(
    "OBO_CONNECTOR", f"projects/{PROJECT_ID}/locations/{LOCATION}/connectors/bigquery-3lo"
)
PROMPT = os.environ.get(
    "OBO_PROMPT", "What finance and marketing data can I personally read? Use my own access."
)

BASE = f"https://{LOCATION}-aiplatform.googleapis.com/v1"
RES = f"projects/{PROJECT_ID}/locations/{LOCATION}/reasoningEngines/{ENGINE_ID}"
STATE = "/tmp/obo_{}.json"


def _token() -> str:
    creds, _ = default()
    creds.refresh(Request())
    return creds.token


def _headers() -> dict:
    return {"Authorization": f"Bearer {_token()}", "Content-Type": "application/json"}


def _query(method: str, body: dict) -> dict:
    r = requests.post(f"{BASE}/{RES}:query", headers=_headers(), json=body)
    r.raise_for_status()
    return r.json()


def _stream(message) -> list:
    """POST :streamQuery, return the list of parsed event dicts."""
    body = {
        "class_method": "stream_query",
        "input": {"user_id": USER_ID, "session_id": SESSION_ID, "message": message},
    }
    r = requests.post(
        f"{BASE}/{RES}:streamQuery?alt=sse", headers=_headers(), json=body, stream=True
    )
    r.raise_for_status()
    events = []
    for line in r.iter_lines():
        if not line:
            continue
        s = line.decode("utf-8").strip()
        if s.startswith("data: "):
            s = s[6:]
        if s in ("", "[DONE]"):
            continue
        try:
            events.append(json.loads(s))
        except json.JSONDecodeError:
            pass
    return events


def _walk_parts(events):
    for e in events:
        for p in (e.get("content", {}) or {}).get("parts", []) or []:
            yield e, p


def _find_auth_request(events):
    for _e, p in _walk_parts(events):
        fc = p.get("function_call") or p.get("functionCall")
        if fc and fc.get("name") == "adk_request_credential":
            return fc
    return None


def _print_texts(events):
    for _e, p in _walk_parts(events):
        if p.get("text"):
            print("   [agent]", p["text"][:600])
        fr = p.get("function_response") or p.get("functionResponse")
        if fr and fr.get("name") != "adk_request_credential":
            print("   [tool]", json.dumps(fr.get("response"))[:600])


def initiate():
    global SESSION_ID
    print(f"== initiate OBO for user_id={USER_ID} ==")
    sess = _query("create_session", {"class_method": "create_session", "input": {"user_id": USER_ID}})
    SESSION_ID = sess["output"]["id"]
    print(f"   session: {SESSION_ID}")

    events = _stream(PROMPT)
    fc = _find_auth_request(events)
    if not fc:
        print("   No adk_request_credential emitted. Raw texts:")
        _print_texts(events)
        print("\n   (If the agent answered without asking for consent, the user may already "
              "have a cached credential, or the tool wasn't called.)")
        return

    args = fc.get("args") or {}
    auth_config = args.get("authConfig") or args.get("auth_config") or args
    blob = json.dumps(auth_config)
    # Pull the consent URL + nonce out of the auth_config wherever they sit.
    auth_uri = _deep_get(auth_config, ("authUri", "auth_uri"))
    nonce = _deep_get(auth_config, ("consentNonce", "consent_nonce", "nonce", "state"))

    state = {
        "session_id": SESSION_ID,
        "fc_id": fc.get("id"),
        "auth_config": auth_config,
        "auth_uri": auth_uri,
        "nonce": nonce,
    }
    with open(STATE.format(USER_ID), "w") as f:
        json.dump(state, f)

    # Prime the Cloud Run callback so its /validateUserId can finalize.
    if CONTINUE_URI and nonce:
        prime_url = CONTINUE_URI.replace("/validateUserId", "/prime")
        pr = requests.post(prime_url, json={"user_id": USER_ID, "consent_nonce": nonce, "connector": CONNECTOR})
        print(f"   primed callback: {pr.status_code} {pr.text[:120]}")
    else:
        print("   WARNING: could not prime (missing CONTINUE_URI or nonce). auth_config dump:")
        print("  ", blob[:800])

    print("\n   >>> OPEN THIS URL, sign in as the matching user, and consent:")
    print("   ", auth_uri or "(auth_uri not found — see auth_config dump above)")
    print(f"\n   Then run:  python scripts/test_obo_agent.py resume {USER_ID}")


def resume():
    global SESSION_ID
    with open(STATE.format(USER_ID)) as f:
        st = json.load(f)
    SESSION_ID = st["session_id"]
    print(f"== resume OBO for user_id={USER_ID} (session {SESSION_ID}) ==")
    message = {
        "role": "user",
        "parts": [
            {
                "function_response": {
                    "id": st["fc_id"],
                    "name": "adk_request_credential",
                    "response": st["auth_config"],
                }
            }
        ],
    }
    events = _stream(message)
    print("   --- agent output after consent ---")
    _print_texts(events)


def _deep_get(obj, keys):
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


if __name__ == "__main__":
    if len(sys.argv) < 3 or sys.argv[1] not in ("initiate", "resume"):
        print("usage: test_obo_agent.py {initiate|resume} <user_id>")
        sys.exit(1)
    if not ENGINE_ID:
        print("AGENT_ENGINE_ID not set; run: source set_env.sh")
        sys.exit(1)
    cmd, USER_ID = sys.argv[1], sys.argv[2]
    SESSION_ID = None
    (initiate if cmd == "initiate" else resume)()
