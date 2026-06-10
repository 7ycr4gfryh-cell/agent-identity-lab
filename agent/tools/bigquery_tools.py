"""
=============================================================================
OneMCP BigQuery Tools for Customer Service Agent - SOLUTION
=============================================================================
Complete implementation of the BigQuery MCP connection.

This is the solution file - compare your implementation against this.
=============================================================================
"""

import os
import ssl

import google.auth
import httpx
from google.auth.transport.requests import Request

# ADK MCP imports
from google.adk.tools.mcp_tool.mcp_toolset import MCPToolset
from google.adk.tools.mcp_tool.mcp_session_manager import StreamableHTTPConnectionParams


# =============================================================================
# Configuration
# =============================================================================

BIGQUERY_MCP_URL = "https://bigquery.googleapis.com/mcp"
# Agent Identity access tokens are certificate-bound: they are only accepted over an mTLS
# channel that presents the agent's workload X.509 cert, so the deployed agent must use the
# mTLS endpoint. Plain-TLS requests with a bound token fail with 401 UNAUTHENTICATED.
BIGQUERY_MCP_MTLS_URL = "https://bigquery.mtls.googleapis.com/mcp"
PROJECT_ID = os.environ.get("GOOGLE_CLOUD_PROJECT") or os.environ.get("PROJECT_ID")
BIGQUERY_SCOPES = ["https://www.googleapis.com/auth/bigquery"]


def _workload_cert_paths():
    """Return (cert_path, key_path) for the Agent Identity workload certs, or None.

    Agent Engine mounts the agent's SPIFFE credentials and points
    GOOGLE_API_CERTIFICATE_CONFIG at them when the engine runs with AGENT_IDENTITY.
    """
    config_path = os.environ.get("GOOGLE_API_CERTIFICATE_CONFIG", "")
    if not config_path or not os.path.exists(config_path):
        return None
    try:
        from google.auth.transport import _mtls_helper
        cert_path, key_path = _mtls_helper._get_workload_cert_and_key_paths(config_path)
        if cert_path and key_path:
            return cert_path, key_path
    except Exception as e:
        print(f"[BigQueryTools] Could not load workload certs: {e}")
    return None


class _RefreshingADCAuth(httpx.Auth):
    """httpx auth that attaches a current ADC access token to every MCP request.

    The toolset can outlive a single access token (~1h), so the token must be refreshed
    per request rather than baked into static headers at startup.
    """

    def __init__(self):
        self._credentials, _ = google.auth.default(scopes=BIGQUERY_SCOPES)

    def _bearer(self) -> str:
        if not self._credentials.valid:
            self._credentials.refresh(Request())
        return f"Bearer {self._credentials.token}"

    def sync_auth_flow(self, request):
        request.headers["Authorization"] = self._bearer()
        yield request

    async def async_auth_flow(self, request):
        request.headers["Authorization"] = self._bearer()
        yield request


def _make_mtls_client_factory(cert_path: str, key_path: str):
    """Build an MCP httpx client factory that presents the agent's workload cert."""

    def factory(headers=None, timeout=None, auth=None) -> httpx.AsyncClient:
        ctx = ssl.create_default_context()
        ctx.load_cert_chain(certfile=cert_path, keyfile=key_path)
        return httpx.AsyncClient(
            verify=ctx,
            follow_redirects=True,
            headers=headers,
            timeout=timeout if timeout is not None else httpx.Timeout(30.0),
            auth=auth or _RefreshingADCAuth(),
        )

    return factory


def get_bigquery_mcp_toolset() -> MCPToolset:
    """
    Create an MCPToolset connected to Google's managed BigQuery MCP server.
    """
    # SOLUTION for TODO 1: Get OAuth credentials
    credentials, project_id = google.auth.default(scopes=BIGQUERY_SCOPES)
    credentials.refresh(Request())
    oauth_token = credentials.token

    # Use environment project if available
    if PROJECT_ID:
        project_id = PROJECT_ID

    cert_paths = _workload_cert_paths()
    if cert_paths:
        # Deployed with Agent Identity: mTLS endpoint + workload cert + per-request token.
        connection_params = StreamableHTTPConnectionParams(
            url=BIGQUERY_MCP_MTLS_URL,
            headers={"x-goog-user-project": project_id},
            httpx_client_factory=_make_mtls_client_factory(*cert_paths),
        )
        print(f"[BigQueryTools] Using mTLS MCP endpoint with workload certs: {cert_paths[0]}")
    else:
        # Local development: plain endpoint with the user's ADC token.
        # SOLUTION for TODO 2: Create headers with OAuth token
        connection_params = StreamableHTTPConnectionParams(
            url=BIGQUERY_MCP_URL,
            headers={
                "Authorization": f"Bearer {oauth_token}",
                "x-goog-user-project": project_id,
            },
        )

    # SOLUTION for TODO 3: Create the MCPToolset
    tools = MCPToolset(connection_params=connection_params)

    print(f"[BigQueryTools] MCP Toolset configured for project: {project_id}")

    return tools


def get_customer_service_instructions() -> str:
    """
    Get additional instructions for the agent about BigQuery access.
    """
    return f"""
## BigQuery Data Access

You have access to customer service data via BigQuery MCP tools.

**Project ID:** {PROJECT_ID}
**Dataset:** customer_service

**Available Tables:**
- `customer_service.customers` - Customer information
- `customer_service.orders` - Order history  
- `customer_service.products` - Product catalog

**Available MCP Tools:**
- `list_table_ids` - Discover what tables exist in a dataset
- `get_table_info` - Get table schema (column names and types)
- `execute_sql` - Run SELECT queries

**IMPORTANT:** Before writing any SQL query, use `get_table_info` to discover 
the exact column names for the table you want to query. Do not guess column names.

**Access Restrictions:**
You only have access to the `customer_service` dataset. You do NOT have access 
to administrative tables like `admin.audit_log`. If a customer asks about admin 
data, politely explain that you only have access to customer service data.
"""


if __name__ == "__main__":
    print("Testing BigQuery MCP connection...")

    try:
        toolset = get_bigquery_mcp_toolset()
        print("✅ BigQuery MCP toolset created successfully!")
        print(f"   Tools available: {toolset}")
    except Exception as e:
        print(f"❌ Error: {e}")
