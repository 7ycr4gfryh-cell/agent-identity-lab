"""
=============================================================================
OneMCP BigQuery Tools for Customer Service Agent
=============================================================================
Connects to Google's managed BigQuery MCP server to provide the agent with
access to customer and order data.

The agent can access:
  ✅ customer_service.customers - Customer information
  ✅ customer_service.orders    - Order history
  ✅ customer_service.products  - Product catalog

The agent CANNOT access (restricted by Agent Identity):
  ❌ admin.audit_log - Administrative audit logs

=============================================================================
YOUR TASK: Implement the placeholder sections marked with TODO
=============================================================================
"""

import os
import google.auth
from google.auth.transport.requests import Request

# ADK MCP imports
from google.adk.tools.mcp_tool.mcp_toolset import MCPToolset
from google.adk.tools.mcp_tool.mcp_session_manager import StreamableHTTPConnectionParams


# =============================================================================
# Configuration
# =============================================================================

# Google's managed BigQuery MCP server endpoint
BIGQUERY_MCP_URL = "https://bigquery.googleapis.com/mcp"

# Get project ID from environment
PROJECT_ID = os.environ.get("GOOGLE_CLOUD_PROJECT") or os.environ.get("PROJECT_ID")


def get_bigquery_mcp_toolset() -> MCPToolset:
    """
    Create an MCPToolset connected to Google's managed BigQuery MCP server.
    
    This function:
    1. Gets OAuth credentials for the current user/service account
    2. Creates a connection to the BigQuery MCP endpoint
    3. Returns an MCPToolset that provides BigQuery query capabilities
    
    The agent will be able to run queries against BigQuery tables that
    its identity (Agent Identity) has access to.
    
    Returns:
        MCPToolset configured for BigQuery access
    """
    # =================================================================
    # TODO 1: Get OAuth credentials
    # =================================================================
    # Use google.auth.default() to get credentials with BigQuery scope
    # Then refresh the credentials to get a valid token
    #
    # Hint:
    #   credentials, project_id = google.auth.default(
    #       scopes=["https://www.googleapis.com/auth/bigquery"]
    #   )
    #   credentials.refresh(Request())
    #   oauth_token = credentials.token
    #
    # Your code here:
    # =================================================================

    oauth_token = None  # PLACEHOLDER - Replace with your implementation
    project_id = PROJECT_ID

    # =================================================================
    # TODO 2: Create headers with OAuth token
    # =================================================================
    # The MCP server needs:
    # - Authorization: Bearer <token>
    # - x-goog-user-project: <project_id>
    #
    # Your code here:
    # headers = { ... }
    # =================================================================

    headers = {}  # PLACEHOLDER - Replace with your implementation

    # =================================================================
    # TODO 3: Create the MCPToolset with StreamableHTTPConnectionParams
    # =================================================================
    # Create an MCPToolset connected to BIGQUERY_MCP_URL
    #
    # Hint:
    #   tools = MCPToolset(
    #       connection_params=StreamableHTTPConnectionParams(
    #           url=BIGQUERY_MCP_URL,
    #           headers=headers,
    #       )
    #   )
    #
    # Your code here:
    # =================================================================

    tools = None  # PLACEHOLDER - Replace with your implementation

    print(f"[BigQueryTools] MCP Toolset configured for project: {project_id}")

    return tools


def get_customer_service_instructions() -> str:
    """
    Get additional instructions for the agent about BigQuery access.

    These instructions tell the agent:
    - What dataset to query
    - How to discover table schemas using MCP tools
    - What the agent CAN and CANNOT access

    Returns:
        Instruction string to append to agent system prompt
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


# =============================================================================
# For testing the connection
# =============================================================================

if __name__ == "__main__":
    print("Testing BigQuery MCP connection...")
    
    try:
        toolset = get_bigquery_mcp_toolset()
        print("✅ BigQuery MCP toolset created successfully!")
        print(f"   Tools available: {toolset}")
    except Exception as e:
        print(f"❌ Error: {e}")
