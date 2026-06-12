"""Chainlit front end: Auth0 login -> Agent Engine + Agent Identity (on-behalf-of-user BigQuery).

Trust domains (same split as mcp-toolbox/adk):
  - Auth0 establishes *identity* only (the signed-in user; no data access).
  - A one-time "Connect Google" consent grants *data access*, brokered by the Agent Identity
    connector + Google's managed credential vault.

Where the substance lives:
  - The agent runs on Vertex AI Agent Engine (we only call stream_query here).
  - At query time the deployed agent uses its own Agent Identity to fetch the user's vaulted
    BigQuery token and query as them. This app never sees that token; it only orchestrates consent.
"""

import chainlit as cl
from chainlit.server import app as fastapi_app
from fastapi import Request
from fastapi.responses import HTMLResponse
from fastapi.routing import APIRoute

import agent_engine_client as engine
import connector_client as connector


@cl.oauth_callback
def oauth_callback(
    provider_id: str,
    token: str,
    raw_user_data: dict,
    default_user: cl.User,
    id_token: str | None = None,
) -> cl.User:
    """Capture identity from Auth0. No data token here — that's the separate consent step."""
    uid = raw_user_data.get("sub") or default_user.identifier
    default_user.identifier = uid
    default_user.metadata["email"] = raw_user_data.get("email") or uid
    return default_user


async def _prompt_status(email: str):
    """Show connection status + the matching action (Connect link or Disconnect button)."""
    uid = cl.user_session.get("uid")
    status, auth_url = connector.status_or_consent(uid)
    connected = status == "connected"
    cl.user_session.set("connected", connected)
    if connected:
        await cl.Message(
            content=(
                f"**Google: connected** (querying BigQuery as **{email}**). "
                f"Ask e.g. *“what finance and marketing data can I read?”*"
            ),
            actions=[cl.Action(name="disconnect", payload={}, label="Disconnect Google")],
        ).send()
    else:
        await cl.Message(
            content=(
                f"**Google: not connected.** Signed in as **{email}**.\n\n"
                f"To let me query BigQuery **as you**, connect your Google account once "
                f"(opens a consent screen):\n\n"
                f"➡️ **[Connect Google (BigQuery)]({auth_url})**\n\n"
                f"After you see *“Credential finalized”*, return and ask your question."
            )
        ).send()


@cl.on_chat_start
async def on_chat_start():
    user: cl.User = cl.user_session.get("user")
    uid = user.identifier
    email = user.metadata.get("email", uid)
    cl.user_session.set("uid", uid)
    cl.user_session.set("email", email)
    cl.user_session.set("session_id", engine.create_session(uid))
    await _prompt_status(email)


@cl.action_callback("disconnect")
async def on_disconnect(action: cl.Action):
    uid = cl.user_session.get("uid")
    ok, detail = connector.revoke(uid)
    cl.user_session.set("connected", False)
    await action.remove()
    if ok:
        await cl.Message(
            content="Disconnected — your BigQuery authorization was revoked. Reconnect below.",
        ).send()
        await _prompt_status(cl.user_session.get("email"))
    else:
        await cl.Message(content=f"Couldn't disconnect: {detail}").send()


@cl.on_message
async def on_message(message: cl.Message):
    uid = cl.user_session.get("uid")
    session_id = cl.user_session.get("session_id")
    email = cl.user_session.get("email")

    # Re-prompt gracefully if consent is missing/expired/revoked (covers the ~7-day
    # Testing-mode refresh-token expiry) instead of letting the query fail confusingly.
    if not cl.user_session.get("connected"):
        status, _ = connector.status_or_consent(uid)
        if status != "connected":
            await _prompt_status(email)
            return
        cl.user_session.set("connected", True)

    out = cl.Message(content="")
    for chunk in engine.stream_text(uid, session_id, message.content):
        await out.stream_token(chunk)
    await out.send()


async def oauth_data_callback(request: Request) -> HTMLResponse:
    """continue_uri: Google redirects the browser here after the user consents."""
    qp = dict(request.query_params)
    uid = qp.get("uid", "")
    validation_state = qp.get("user_id_validation_state", "")
    if not uid or not validation_state:
        return HTMLResponse(_page("Missing consent parameters."), status_code=400)
    ok, detail = connector.finalize(uid, validation_state)
    msg = "Credential finalized." if ok else f"Finalize failed: {detail}"
    return HTMLResponse(_page(msg), status_code=(200 if ok else 502))


# Insert ahead of Chainlit's SPA catch-all so this route actually matches.
fastapi_app.router.routes.insert(
    0, APIRoute("/oauth/callback", oauth_data_callback, methods=["GET"])
)


def _page(message: str) -> str:
    return (
        f"<!doctype html><html><body style='font-family:sans-serif'>"
        f"<h3>{message}</h3>"
        f"<p>You can close this tab and return to the chat.</p>"
        f"<script>setTimeout(function(){{window.close()}},1200)</script>"
        f"</body></html>"
    )
