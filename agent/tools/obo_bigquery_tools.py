"""
=============================================================================
On-behalf-of-user (3-legged OAuth) BigQuery tool
=============================================================================
Demonstrates the OTHER Agent Identity flow: instead of calling BigQuery as the
agent's own identity, the agent calls BigQuery AS THE CONSENTING END USER via a
delegated OAuth token brokered by an Agent Identity connector (3LO).

Access therefore follows the *human*, not the agent:
  - behbooei@gmail.com     -> READER on demo_finance.revenue
  - mr.behbooei@gmail.com  -> READER on demo_marketing.campaigns
The agent's own identity can read neither — that's the contrast this proves.

Wiring:
  - CredentialManager.register_auth_provider(GcpAuthProvider()) makes ADK route
    GcpAuthProviderScheme credential requests through the IAM connector service.
  - AuthenticatedFunctionTool injects the delegated `credential` into the tool
    function after the user consents (see the consent round-trip in
    scripts/test_obo_agent.py and the Cloud Run continue_uri in obo_callback/).
=============================================================================
"""

import os

import httpx
from google.adk.auth.auth_credential import AuthCredential
from google.adk.auth.auth_tool import AuthConfig
from google.adk.auth.credential_manager import CredentialManager
from google.adk.integrations.agent_identity import (
    GcpAuthProvider,
    GcpAuthProviderScheme,
)
from google.adk.tools.authenticated_function_tool import AuthenticatedFunctionTool
from google.api_core.client_options import ClientOptions
from google.cloud.iamconnectorcredentials_v1alpha import (
    IAMConnectorCredentialsServiceClient,
)

PROJECT_ID = os.environ.get("GOOGLE_CLOUD_PROJECT") or os.environ.get("PROJECT_ID")
LOCATION = os.environ.get("GOOGLE_CLOUD_LOCATION", "us-central1")

# The pre-created BigQuery 3LO connector (allowed scope includes .../auth/bigquery).
OBO_CONNECTOR = os.environ.get(
    "OBO_CONNECTOR",
    f"projects/{PROJECT_ID}/locations/{LOCATION}/connectors/bigquery-3lo",
)
# The Cloud Run continue_uri that finalizes consent (obo_callback service).
OBO_CONTINUE_URI = os.environ.get("OBO_CONTINUE_URI", "")
# Request the full bigquery scope (it is in the connector's allowed-scopes list).
OBO_SCOPES = ["https://www.googleapis.com/auth/bigquery"]

# Datasets to probe — each gated by a different user's dataset-level READER grant.
_DATASETS = [
    ("demo_finance", "revenue"),
    ("demo_marketing", "campaigns"),
]

class _FreshClientGcpAuthProvider(GcpAuthProvider):
    """GcpAuthProvider that builds a fresh iamconnectorcredentials client per call.

    The stock provider caches one REST client. Its google-auth mTLS adapter builds a
    single pyOpenSSL SSL context for the agent's certificate-bound token; pyOpenSSL
    freezes that context after the first connection, so the *second* retrieveCredentials
    (e.g. resuming after consent) fails with "Context has already been used to create a
    Connection, it cannot be mutated again". A fresh client => fresh mTLS context per
    call, so each retrieve gets its own one-shot context.
    """

    def _get_client(self):  # noqa: D401 - overrides cached client construction
        client_options = None
        host = os.environ.get("IAM_CONNECTOR_CREDENTIALS_TARGET_HOST")
        if host:
            client_options = ClientOptions(api_endpoint=host)
        return IAMConnectorCredentialsServiceClient(
            client_options=client_options, transport="rest"
        )


# Register the Agent Identity auth provider once, at import time.
CredentialManager.register_auth_provider(_FreshClientGcpAuthProvider())


def _obo_auth_config() -> AuthConfig:
    return AuthConfig(
        auth_scheme=GcpAuthProviderScheme(
            name=OBO_CONNECTOR,
            continue_uri=OBO_CONTINUE_URI,
            scopes=OBO_SCOPES,
        )
    )


def _extract_token(credential: AuthCredential) -> str | None:
    if credential is None:
        return None
    if credential.http and credential.http.credentials:
        return credential.http.credentials.token
    if credential.oauth2 and credential.oauth2.access_token:
        return credential.oauth2.access_token
    return None


async def read_my_datasets(credential: AuthCredential) -> dict:
    """Read the caller's finance and marketing demo tables on their behalf.

    Use this when the user asks what finance or marketing data they can see, or
    to check their own access. The data is read with the user's delegated
    credentials, so results depend on which datasets that user can read.
    """
    token = _extract_token(credential)
    if not token:
        return {"error": "No delegated user token available; consent not completed."}

    results = {}
    headers = {"Authorization": f"Bearer {token}"}
    async with httpx.AsyncClient(timeout=30) as client:
        for dataset, table in _DATASETS:
            url = (
                f"https://bigquery.googleapis.com/bigquery/v2/projects/{PROJECT_ID}"
                f"/datasets/{dataset}/tables/{table}/data?maxResults=5"
            )
            try:
                resp = await client.get(url, headers=headers)
            except Exception as e:  # noqa: BLE001
                results[f"{dataset}.{table}"] = {"status": "error", "detail": str(e)[:200]}
                continue
            if resp.status_code == 200:
                body = resp.json()
                results[f"{dataset}.{table}"] = {
                    "status": "ALLOWED",
                    "row_count": int(body.get("totalRows", "0")),
                }
            else:
                # 403 here means the consenting user lacks READER on this dataset.
                msg = ""
                try:
                    msg = resp.json().get("error", {}).get("message", "")
                except Exception:  # noqa: BLE001
                    msg = resp.text[:200]
                results[f"{dataset}.{table}"] = {
                    "status": f"DENIED ({resp.status_code})",
                    "detail": msg[:200],
                }
    return {"read_as": "the consenting end user (3LO on-behalf-of)", "datasets": results}


def get_obo_bigquery_tool() -> AuthenticatedFunctionTool:
    """Build the on-behalf-of-user BigQuery tool."""
    return AuthenticatedFunctionTool(
        func=read_my_datasets,
        auth_config=_obo_auth_config(),
        response_for_auth_required="Pending user authorization (3-legged OAuth consent).",
    )
