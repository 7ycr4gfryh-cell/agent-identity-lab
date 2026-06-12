"""Gateway-native agent: two BigQuery MCP backends, switchable, all governance on the platform.

Cloud-native stamp (no hand-rolled auth/guards):
- Tools come from the **Agent Registry** via `AgentRegistry.get_mcp_toolset()`, which auto-resolves each
  server's binding (auth provider `bigquery-3lo`) into a `GcpAuthProviderScheme`. The ADK + Agent
  Identity broker the per-user OBO token; this module carries NO auth/header/mTLS code.
- Egress to each MCP server is governed by the **egress Agent Gateway** (default-deny IAM + Model Armor).
- Two backends are exposed — native Google BigQuery MCP and the Toolbox MCP — and the UI switches
  between them per session via the `mcp_backend` state key; a `before_tool_callback` enforces that only
  the active backend is callable (one active at a time).
- No in-code Model Armor: ingress/egress Model Armor run at the gateways.
"""

import os

from google.adk.agents import LlmAgent
from google.adk.auth.credential_manager import CredentialManager
from google.adk.integrations.agent_identity import GcpAuthProvider
from google.adk.integrations.agent_registry import AgentRegistry

PROJECT_ID = os.environ.get("GOOGLE_CLOUD_PROJECT") or os.environ.get("PROJECT_ID")
LOCATION = os.environ.get("GOOGLE_CLOUD_LOCATION", "us-central1")
CONTINUE_URI = os.environ.get("OBO_CONTINUE_URI", "")  # Chainlit /oauth/callback (consent redirect)
DEFAULT_BACKEND = os.environ.get("DEFAULT_MCP_BACKEND", "toolbox")

# Registered MCP server resource names (Agent Registry mcpServers/...).
MCP_TOOLBOX = os.environ.get(
    "MCP_TOOLBOX_SERVER",
    f"projects/{PROJECT_ID}/locations/{LOCATION}/mcpServers/agentregistry-00000000-0000-0000-9ff6-85dbf859559a",
)
MCP_NATIVE = os.environ.get(
    "MCP_NATIVE_SERVER",
    f"projects/{PROJECT_ID}/locations/{LOCATION}/mcpServers/agentregistry-00000000-0000-0000-050d-4a33cbd4a264",
)

# The Agent Identity auth provider used by the registry-resolved GcpAuthProviderScheme.
CredentialManager.register_auth_provider(GcpAuthProvider())


def _build_toolsets():
    """Build both registry toolsets; return (tools, backend->prefix map)."""
    reg = AgentRegistry(project_id=PROJECT_ID, location=LOCATION)
    toolbox = reg.get_mcp_toolset(MCP_TOOLBOX, continue_uri=CONTINUE_URI)
    native = reg.get_mcp_toolset(MCP_NATIVE, continue_uri=CONTINUE_URI)
    prefixes = {
        "toolbox": getattr(toolbox, "tool_name_prefix", "") or "",
        "native": getattr(native, "tool_name_prefix", "") or "",
    }
    return [toolbox, native], prefixes


_TOOLS, _PREFIXES = _build_toolsets()


def _active_backend(state) -> str:
    try:
        return state.get("mcp_backend") or DEFAULT_BACKEND
    except Exception:  # noqa: BLE001
        return DEFAULT_BACKEND


def _before_model(callback_context, llm_request):
    """Steer the model toward the active backend (enforcement is in before_tool)."""
    backend = _active_backend(callback_context.state)
    prefix = _PREFIXES.get(backend, "")
    note = (
        f"[ACTIVE DATA BACKEND: {backend}. Use ONLY tools whose name starts with "
        f"'{prefix}'. Ignore the other backend's tools.]"
    )
    try:
        from google.genai import types
        llm_request.contents = list(llm_request.contents or [])
        llm_request.contents.append(
            types.Content(role="user", parts=[types.Part(text=note)])
        )
    except Exception:  # noqa: BLE001
        pass
    return None


def _before_tool(tool, args, tool_context):
    """Hard-enforce one-active-backend: block calls to the non-selected backend's tools."""
    backend = _active_backend(tool_context.state)
    active_prefix = _PREFIXES.get(backend, "")
    name = getattr(tool, "name", "")
    other_prefix = _PREFIXES.get("native" if backend == "toolbox" else "toolbox", "")
    if other_prefix and name.startswith(other_prefix):
        return {
            "error": (
                f"The '{backend}' BigQuery MCP backend is active; '{name}' belongs to the other "
                f"backend. Use the '{active_prefix}' tools, or switch backend in the UI."
            )
        }
    return None


def get_instructions() -> str:
    return (
        "You are a data assistant for the signed-in user. Answer questions about BigQuery data using "
        "ONLY the tools for the currently active backend (see the ACTIVE DATA BACKEND note). Briefly "
        "say what you'll do, then summarize results in plain language.\n"
        "If a tool returns access-denied/403, explain the signed-in user's access doesn't cover that "
        "data. If a tool reports no credential / pending authorization, tell the user to click Connect "
        "in the app. Two backends exist (native Google BigQuery MCP and the Toolbox MCP); the user "
        "picks one in the UI."
    )


def create_agent() -> LlmAgent:
    return LlmAgent(
        model="gemini-2.5-flash",
        name="bq_gateway_agent",
        instruction=get_instructions(),
        tools=_TOOLS,
        before_model_callback=_before_model,
        before_tool_callback=_before_tool,
    )


_RUNNING_IN_AGENT_ENGINE = os.environ.get("AGENT_ENGINE_RUNTIME", "").lower() == "true"
root_agent = None if _RUNNING_IN_AGENT_ENGINE else create_agent()
