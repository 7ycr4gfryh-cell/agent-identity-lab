"""Agent Engine wrapper for the gateway-native agent (lazy agent creation)."""

import os

os.environ["AGENT_ENGINE_RUNTIME"] = "true"

from vertexai import agent_engines
from .agent import create_agent

# Tracing left off (same boot-time Resource Manager 401 race as the other engine until identity
# is provisioned). Gateway exposes its own OpenTelemetry traces anyway.
app = agent_engines.AdkApp(
    agent=create_agent,
    enable_tracing=False,
)
