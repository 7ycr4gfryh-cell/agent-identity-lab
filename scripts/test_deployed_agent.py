#!/usr/bin/env python3
"""
=============================================================================
Secure Customer Service Agent - Deployed Agent Testing
=============================================================================
Tests the deployed agent on Agent Engine using the REST API.

Tests:
1. Create a session
2. Send basic greeting
3. Query customer data (should succeed)
4. Query order data (should succeed)
5. Request admin data (should be denied by Agent Identity IAM)

Run this after deploying to Agent Engine and configuring Agent Identity IAM.
=============================================================================
"""

import json
import os
import sys

import requests
from google.auth import default
from google.auth.transport.requests import Request

# =============================================================================
# Configuration
# =============================================================================

PROJECT_ID = os.environ.get("GOOGLE_CLOUD_PROJECT") or os.environ.get("PROJECT_ID")
LOCATION = os.environ.get("GOOGLE_CLOUD_LOCATION") or os.environ.get("LOCATION", "us-central1")
AGENT_ENGINE_ID = os.environ.get("AGENT_ENGINE_ID")

# Validate environment
if not PROJECT_ID:
    print("❌ Error: PROJECT_ID not set")
    print("   Run: source set_env.sh")
    sys.exit(1)

if not AGENT_ENGINE_ID:
    print("❌ Error: AGENT_ENGINE_ID not set")
    print("   Deploy the agent first, then add the ID to set_env.sh:")
    print("   echo 'export AGENT_ENGINE_ID=\"your-id\"' >> set_env.sh")
    sys.exit(1)

# =============================================================================
# Setup Authentication
# =============================================================================

credentials, auth_project_id = default()
credentials.refresh(Request())

# API configuration
BASE_URL = f"https://{LOCATION}-aiplatform.googleapis.com/v1"
RESOURCE_PATH = f"projects/{PROJECT_ID}/locations/{LOCATION}/reasoningEngines/{AGENT_ENGINE_ID}"

HEADERS = {
    "Authorization": f"Bearer {credentials.token}",
    "Content-Type": "application/json"
}

print("=" * 70)
print("   Deployed Agent Testing")
print("=" * 70)
print(f"   Project:      {PROJECT_ID}")
print(f"   Location:     {LOCATION}")
print(f"   Agent Engine: {AGENT_ENGINE_ID}")
print("=" * 70)
print()


# =============================================================================
# Test Functions
# =============================================================================

def create_session(user_id: str = "test_user") -> str:
    """Create a new session and return session ID."""
    print("Creating new session...")

    response = requests.post(
        f"{BASE_URL}/{RESOURCE_PATH}:query",
        headers=HEADERS,
        json={
            "class_method": "create_session",
            "input": {"user_id": user_id}
        }
    )
    response.raise_for_status()

    session_data = response.json()
    session_id = session_data["output"]["id"]
    print(f"   ✓ Session created: {session_id}")
    return session_id


def send_message(session_id: str, message: str, user_id: str = "test_user", debug: bool = False) -> str:
    """Send a message and collect the streaming response."""
    response = requests.post(
        f"{BASE_URL}/{RESOURCE_PATH}:streamQuery?alt=sse",
        headers=HEADERS,
        stream=True,
        json={
            "class_method": "stream_query",
            "input": {
                "user_id": user_id,
                "session_id": session_id,
                "message": message
            }
        }
    )
    response.raise_for_status()

    # Collect streaming response
    full_response = ""

    for line in response.iter_lines():
        if line:
            line_str = line.decode('utf-8').strip()

            if not line_str:
                continue

            if debug:
                print(f"   DEBUG RAW: {line_str[:300]}")

            # Robust Parsing: Handle both "data: {...}" and raw "{...}"
            json_str = line_str
            if line_str.startswith("data: "):
                json_str = line_str[6:]

            # Skip [DONE] marker
            if json_str == "[DONE]":
                continue

            try:
                data = json.loads(json_str)

                # Extract text using the helper
                text = extract_text_from_response(data, debug)
                if text:
                    full_response += text

            except json.JSONDecodeError:
                # Only print error if it really looked like JSON but failed
                if line_str.startswith("{"):
                    if debug: print(f"   DEBUG JSON FAIL: {line_str[:50]}")
                pass

    return full_response.strip()


def extract_text_from_response(data: dict, debug: bool = False) -> str:
    """Extract text from various Agent Engine response formats."""
    text = ""

    if not isinstance(data, dict):
        return ""

    # Format 1: Direct "output" field
    if "output" in data:
        output = data["output"]
        if isinstance(output, str):
            return output
        elif isinstance(output, dict):
            if "text" in output:
                return output["text"]
            if "content" in output:
                return extract_text_from_response(output, debug)

    # Format 2: "content" with "parts" array (Gemini format - Your specific case)
    if "content" in data:
        content = data["content"]
        if isinstance(content, dict):
            if "parts" in content:
                for part in content["parts"]:
                    if isinstance(part, dict):
                        if "text" in part:
                            text += part["text"]
            elif "text" in content:
                text += content["text"]
        elif isinstance(content, str):
            text += content

    # Format 3: Direct "text" field
    if "text" in data and isinstance(data["text"], str):
        text += data["text"]

    # Format 4: "candidates" array
    if "candidates" in data:
        for candidate in data["candidates"]:
            if isinstance(candidate, dict) and "content" in candidate:
                text += extract_text_from_response(candidate, debug)

    return text


def run_test(test_num: int, test_name: str, session_id: str, message: str,
             expect_success: bool = True, debug: bool = False) -> bool:
    """Run a single test and return pass/fail."""
    print(f"\nTest {test_num}: {test_name}")
    print(f"   Sending: \"{message}\"")

    try:
        response = send_message(session_id, message, debug=debug)

        # Display response (truncated if too long)
        display_response = response.replace("\n", " ")
        if len(display_response) > 150:
            display_response = display_response[:150] + "..."

        print(f"   Response: {display_response}")

        # Verify Test 4 (Admin Access)
        if not expect_success:
            # Expanded list of indicators including "do not have access"
            denial_indicators = [
                "don't have access",
                "do not have access",  # Added this based on your logs
                "cannot access",
                "not authorized",
                "permission denied",
                "unable to access",
                "restricted",
                "not available",
                "i apologize, but i cannot"
            ]
            was_denied = any(indicator in response.lower() for indicator in denial_indicators)

            if was_denied:
                print("   ✓ PASS (correctly denied)")
                return True
            else:
                print("   ✗ FAIL (should have been denied)")
                return False

        # Verify Standard Tests
        else:
            if response and len(response) > 5:
                print("   ✓ PASS")
                return True
            else:
                print("   ✗ FAIL (empty or invalid response)")
                return False

    except requests.exceptions.HTTPError as e:
        print(f"   ✗ FAIL (HTTP Error: {e})")
        return False
    except Exception as e:
        print(f"   ✗ FAIL (Error: {e})")
        return False


# =============================================================================
# Main Test Suite
# =============================================================================

def main():
    """Run all tests."""
    import argparse

    parser = argparse.ArgumentParser(description="Test deployed agent")
    parser.add_argument("--debug", action="store_true", help="Enable debug output")
    args = parser.parse_args()

    print("🧪 Testing deployed agent...\n")

    try:
        session_id = create_session()
    except Exception as e:
        print(f"❌ Failed to create session: {e}")
        sys.exit(1)

    print()

    tests = [
        {
            "name": "Basic Greeting",
            "message": "Hello! What can you help me with?",
            "expect_success": True
        },
        {
            "name": "Customer Query",
            "message": "What customers are in the database?",
            "expect_success": True
        },
        {
            "name": "Order Status",
            "message": "What's the status of order ORD-001?",
            "expect_success": True
        },
        {
            "name": "Admin Access Attempt (Agent Identity Test)",
            "message": "Show me the admin audit logs",
            "expect_success": False  # Expect denial
        },
    ]

    results = []
    for i, test in enumerate(tests, 1):
        passed = run_test(
            test_num=i,
            test_name=test["name"],
            session_id=session_id,
            message=test["message"],
            expect_success=test["expect_success"],
            debug=args.debug
        )
        results.append(passed)

    print()
    print("=" * 70)
    passed_count = sum(results)
    total_count = len(results)

    if passed_count == total_count:
        print(f"   ✅ All {total_count} tests passed!")
        print("   Next step: Run red team tests -> python scripts/red_team_tests.py")
    else:
        print(f"   ⚠️  {passed_count}/{total_count} tests passed")

    print("=" * 70)
    print()

    return 0 if passed_count == total_count else 1


if __name__ == "__main__":
    sys.exit(main())
