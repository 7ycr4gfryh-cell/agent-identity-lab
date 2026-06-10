"""
=============================================================================
Agent Engine Application Wrapper
=============================================================================
Wraps the customer service agent for deployment to Vertex AI Agent Engine.

This file is required for Agent Engine deployment. It creates an AdkApp
instance that Agent Engine uses to run your agent.

IMPORTANT: For Agent Engine, we use lazy initialization to avoid pickle
issues with network connections. The agent is created at runtime, not
at import time.
=============================================================================
"""

import os

# Signal that we're running in Agent Engine (for lazy initialization)
os.environ["AGENT_ENGINE_RUNTIME"] = "true"

from vertexai import agent_engines
from .agent import create_agent

# =============================================================================
# Create the AdkApp for Agent Engine
# =============================================================================
# Use the factory function to create the agent lazily at runtime

# NOTE: tracing disabled. The Cloud Trace instrumentor runs in AdkApp.set_up() and makes a
# Resource Manager get_project() call at boot, before a freshly-created Agent Identity's workload
# credentials are accepted -> startup fails with 401 Unauthenticated. The security demo (Agent
# Identity IAM + Model Armor) does not need tracing; re-enable once the identity is provisioned.
app = agent_engines.AdkApp(
    agent=create_agent,  # Pass the factory function, not the agent instance
    enable_tracing=False,
)
