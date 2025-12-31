#!/usr/bin/env python3
"""
=============================================================================
Secure Customer Service Agent - Model Armor Template Creation
=============================================================================
Creates a Model Armor security template with the following protections:

1. Prompt Injection & Jailbreak Detection (LOW_AND_ABOVE - most sensitive)
2. Sensitive Data Protection (SSN, credit cards, API keys)
3. Responsible AI Filters (harassment, hate speech, dangerous content)
4. Malicious URL Detection (based on threat intelligence)

Run this script after setup_env.sh to create your security template.
=============================================================================
"""

import os
import sys
import time
from datetime import datetime

# =============================================================================
# Configuration
# =============================================================================

PROJECT_ID = os.environ.get("GOOGLE_CLOUD_PROJECT") or os.environ.get("PROJECT_ID")
LOCATION = os.environ.get("GOOGLE_CLOUD_LOCATION") or os.environ.get("LOCATION") or "us-central1"

if not PROJECT_ID:
    import subprocess
    PROJECT_ID = subprocess.check_output(
        ["gcloud", "config", "get-value", "project"],
        text=True
    ).strip()

print("=" * 70)
print("   Model Armor Template Creation")
print("=" * 70)
print(f"   Project:  {PROJECT_ID}")
print(f"   Location: {LOCATION}")
print("=" * 70)
print()

# =============================================================================
# Import Model Armor SDK
# =============================================================================

try:
    from google.cloud import modelarmor_v1
    from google.api_core.client_options import ClientOptions
except ImportError:
    print("❌ Error: google-cloud-modelarmor not installed.")
    print("   Run: pip install google-cloud-modelarmor")
    sys.exit(1)

# =============================================================================
# Create Model Armor Client
# =============================================================================

print("📡 Connecting to Model Armor API...")

client = modelarmor_v1.ModelArmorClient(
    transport="rest",
    client_options=ClientOptions(
        api_endpoint=f"modelarmor.{LOCATION}.rep.googleapis.com"
    ),
)

print("   ✓ Connected successfully")
print()

# =============================================================================
# Define Security Template
# =============================================================================

print("🛡️ Configuring security template...")
print()
print("   Detection Settings:")
print("   ┌─────────────────────────────────────────────────────────────┐")
print("   │ Filter                    │ Setting              │ Level   │")
print("   ├─────────────────────────────────────────────────────────────┤")
print("   │ Prompt Injection          │ ENABLED              │ LOW+    │")
print("   │ Jailbreak Detection       │ ENABLED              │ LOW+    │")
print("   │ Sensitive Data (SDP)      │ ENABLED              │ -       │")
print("   │ Malicious URLs            │ ENABLED              │ -       │")
print("   │ Harassment                │ ENABLED              │ LOW+    │")
print("   │ Hate Speech               │ ENABLED              │ MEDIUM+ │")
print("   │ Dangerous Content         │ ENABLED              │ MEDIUM+ │")
print("   │ Sexually Explicit         │ ENABLED              │ MEDIUM+ │")
print("   └─────────────────────────────────────────────────────────────┘")
print()

template = modelarmor_v1.Template(
    filter_config=modelarmor_v1.FilterConfig(
        # =====================================================================
        # 1. Prompt Injection & Jailbreak Detection
        # =====================================================================
        # LOW_AND_ABOVE = Most sensitive, catches subtle injection attempts
        # This is critical for customer service agents that handle user input
        pi_and_jailbreak_filter_settings=modelarmor_v1.PiAndJailbreakFilterSettings(
            filter_enforcement=modelarmor_v1.PiAndJailbreakFilterSettings.PiAndJailbreakFilterEnforcement.ENABLED,
            confidence_level=modelarmor_v1.DetectionConfidenceLevel.LOW_AND_ABOVE,
        ),
        
        # =====================================================================
        # 2. Malicious URL Detection
        # =====================================================================
        # Detects known malicious URLs based on Google's threat intelligence
        # Note: Only catches URLs in actual threat databases, not "suspicious looking" URLs
        malicious_uri_filter_settings=modelarmor_v1.MaliciousUriFilterSettings(
            filter_enforcement=modelarmor_v1.MaliciousUriFilterSettings.MaliciousUriFilterEnforcement.ENABLED,
        ),
        
        # =====================================================================
        # 3. Sensitive Data Protection (SDP)
        # =====================================================================
        # Detects: SSN, credit cards, API keys, financial account numbers
        # Uses basic configuration for common PII types
        sdp_settings=modelarmor_v1.SdpFilterSettings(
            basic_config=modelarmor_v1.SdpBasicConfig(
                filter_enforcement=modelarmor_v1.SdpBasicConfig.SdpBasicConfigEnforcement.ENABLED
            )
        ),
        
        # =====================================================================
        # 4. Responsible AI Filters
        # =====================================================================
        # Filter harmful content in both prompts and responses
        rai_settings=modelarmor_v1.RaiFilterSettings(
            rai_filters=[
                # Dangerous content (weapons, self-harm, etc.)
                modelarmor_v1.RaiFilterSettings.RaiFilter(
                    filter_type=modelarmor_v1.RaiFilterType.DANGEROUS,
                    confidence_level=modelarmor_v1.DetectionConfidenceLevel.MEDIUM_AND_ABOVE,
                ),
                # Hate speech
                modelarmor_v1.RaiFilterSettings.RaiFilter(
                    filter_type=modelarmor_v1.RaiFilterType.HATE_SPEECH,
                    confidence_level=modelarmor_v1.DetectionConfidenceLevel.MEDIUM_AND_ABOVE,
                ),
                # Harassment - more sensitive for customer service context
                modelarmor_v1.RaiFilterSettings.RaiFilter(
                    filter_type=modelarmor_v1.RaiFilterType.HARASSMENT,
                    confidence_level=modelarmor_v1.DetectionConfidenceLevel.LOW_AND_ABOVE,
                ),
                # Sexually explicit content
                modelarmor_v1.RaiFilterSettings.RaiFilter(
                    filter_type=modelarmor_v1.RaiFilterType.SEXUALLY_EXPLICIT,
                    confidence_level=modelarmor_v1.DetectionConfidenceLevel.MEDIUM_AND_ABOVE,
                ),
            ]
        ),
    ),
)

# =============================================================================
# Create Template
# =============================================================================

# Generate unique template ID with timestamp
template_id = f"cs_agent_security_{datetime.now().strftime('%Y%m%d_%H%M%S')}"

print(f"📝 Creating template: {template_id}")
print()

try:
    response = client.create_template(
        parent=f"projects/{PROJECT_ID}/locations/{LOCATION}",
        template_id=template_id,
        template=template,
    )
    
    TEMPLATE_NAME = response.name
    
    print("✅ Template created successfully!")
    print()
    print(f"   Template Name: {TEMPLATE_NAME}")
    print()
    
    # Wait for template to activate
    print("   ⏳ Waiting for template to activate...")
    time.sleep(3)
    print("   ✓ Template ready!")
    print()
    
    # =============================================================================
    # Update Environment File
    # =============================================================================
    
    script_dir = os.path.dirname(os.path.abspath(__file__))
    repo_dir = os.path.dirname(script_dir)
    env_file = os.path.join(repo_dir, "set_env.sh")
    
    if os.path.exists(env_file):
        with open(env_file, "r") as f:
            content = f.read()
        
        # Update TEMPLATE_NAME
        content = content.replace(
            'export TEMPLATE_NAME=""',
            f'export TEMPLATE_NAME="{TEMPLATE_NAME}"'
        )
        
        with open(env_file, "w") as f:
            f.write(content)
        
        print(f"   ✓ Updated {env_file} with TEMPLATE_NAME")
        print()
    
    # =============================================================================
    # Summary
    # =============================================================================
    
    print("=" * 70)
    print("   Next Steps")
    print("=" * 70)
    print()
    print("   1. Reload environment variables:")
    print("      source set_env.sh")
    print()
    print("   2. Test the template standalone:")
    print("      python setup/test_template.py")
    print()
    print("   3. Implement the Model Armor plugin:")
    print("      Edit: agent/plugins/model_armor_plugin.py")
    print()

except Exception as e:
    print(f"❌ Error creating template: {e}")
    print()
    print("   Common issues:")
    print("   - Model Armor API not enabled")
    print("   - Insufficient permissions")
    print("   - Invalid location")
    print()
    print("   Try: gcloud services enable modelarmor.googleapis.com")
    sys.exit(1)
