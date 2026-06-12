"""Create an EMPTY Agent Engine attached to BOTH gateways (egress + ingress) with Agent Identity.

Two-step deploy (same as the original): create the engine shell here (so identity + gateway config
are set at create time), then `adk deploy agent_engine --agent_engine_id <id> agent_gw` pushes code.
Prints the new engine id + its Agent Identity principal for the subsequent bindings/IAM steps.
"""

import os
import sys

import vertexai
from vertexai import types

PROJECT = os.environ["GOOGLE_CLOUD_PROJECT"]
LOCATION = os.environ.get("GOOGLE_CLOUD_LOCATION", "us-central1")

# NOTE: identity_type is set at create; the gateway config (agent_gateway_config) can only be set in
# the SAME call that ships source code (SDK validation). So we create an identity-only shell here,
# then `adk deploy ... --agent_engine_config_file .agent_engine_config.json` attaches the gateways
# during the code-bearing update.
client = vertexai.Client(
    project=PROJECT, location=LOCATION, http_options=dict(api_version="v1beta1")
)

print("Creating Agent-Identity engine shell (gateways attached at adk deploy)...")
remote = client.agent_engines.create(
    config={
        "identity_type": types.IdentityType.AGENT_IDENTITY,
        "display_name": "BQ Gateway Agent (egress+ingress)",
    }
)

res = getattr(remote, "api_resource", None)
name = getattr(res, "name", None) or getattr(remote, "name", "")
engine_id = name.split("/")[-1] if name else "?"
eff = getattr(getattr(res, "spec", None), "effective_identity", None)
print(f"ENGINE_ID={engine_id}")
print(f"EFFECTIVE_IDENTITY={eff}")
print(f"FULL_NAME={name}")
if engine_id == "?":
    sys.exit("Could not extract engine id; check console.")
