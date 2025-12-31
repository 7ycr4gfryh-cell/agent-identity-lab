#!/usr/bin/env python3
"""
Billing Enablement Script for Secure Agent Codelab

Automatically links a billing account to the current Google Cloud project.
Based on battle-tested patterns from Google Cloud codelabs.

This script handles common workshop scenarios:
- API propagation delays after enabling
- Billing account propagation delays (when credits are just claimed)
- Verification that billing link is actually active

Usage: Called by setup_env.sh, or run directly: python3 billing_enablement.py
"""

import importlib
import os
import subprocess
import sys
import time


def install_and_import_billing():
    """Install google-cloud-billing if needed and import it."""
    try:
        from google.cloud import billing_v1
        from google.api_core import exceptions
        return billing_v1, exceptions
    except ImportError:
        pass

    # Package not found - install it
    print("Installing google-cloud-billing...")
    subprocess.check_call([
        sys.executable, "-m", "pip", "install",
        "--quiet", "--disable-pip-version-check",
        "google-cloud-billing"
    ])

    # Clear Python's import cache so it finds the newly installed package
    importlib.invalidate_caches()

    # For namespace packages like google.cloud, we may need to reload
    if 'google' in sys.modules:
        importlib.reload(sys.modules['google'])
    if 'google.cloud' in sys.modules:
        importlib.reload(sys.modules['google.cloud'])

    # Now import
    from google.cloud import billing_v1
    from google.api_core import exceptions
    return billing_v1, exceptions


# Import billing modules (installing if necessary)
billing_v1, exceptions = install_and_import_billing()


def get_project_id() -> str:
    """Get the current Google Cloud project ID from gcloud config."""
    try:
        result = subprocess.run(
            ["gcloud", "config", "get-value", "project"],
            capture_output=True, text=True, timeout=10
        )
        project_id = result.stdout.strip()
        if project_id and project_id != "(unset)":
            return project_id
    except (subprocess.TimeoutExpired, FileNotFoundError):
        pass

    print("❌ Error: No Google Cloud project configured.")
    print("   Run: gcloud config set project YOUR_PROJECT_ID")
    sys.exit(1)


def enable_billing_api(project_id: str) -> bool:
    """Enable the Cloud Billing API using gcloud."""
    print("   Enabling Cloud Billing API...")
    try:
        subprocess.run(
            ["gcloud", "services", "enable", "cloudbilling.googleapis.com",
             "--project", project_id, "--quiet"],
            check=True, capture_output=True, text=True, timeout=60
        )
        print("   ✓ Cloud Billing API enabled")
        return True
    except FileNotFoundError:
        print("   ❌ Error: 'gcloud' command not found")
        return False
    except subprocess.CalledProcessError as e:
        print(f"   ❌ Error enabling API: {e.stderr}")
        return False
    except subprocess.TimeoutExpired:
        print("   ❌ Timeout enabling API")
        return False


def get_billing_accounts(client: billing_v1.CloudBillingClient):
    """Fetch billing accounts with error handling for API/permission issues."""
    try:
        accounts = client.list_billing_accounts()
        return list(accounts)
    except exceptions.PermissionDenied as e:
        error_message = e.message.lower()
        if "api has not been used" in error_message or "service is disabled" in error_message:
            # API not yet propagated - this is recoverable
            return "API_DISABLED_OR_PROPAGATING"
        else:
            # Actual permission issue
            print(f"   ❌ Permission denied: {e.message}")
            return "PERMISSION_DENIED"
    except Exception as e:
        print(f"   ❌ Unexpected error: {e}")
        return "UNEXPECTED_ERROR"


def check_current_billing(client: billing_v1.CloudBillingClient, project_id: str) -> tuple:
    """Check if project already has billing enabled. Returns (is_enabled, account_name)."""
    project_name = f"projects/{project_id}"
    try:
        info = client.get_project_billing_info(name=project_name)
        if info.billing_enabled:
            return True, info.billing_account_name
        return False, None
    except exceptions.NotFound:
        return False, None
    except Exception:
        return False, None


def link_billing_account(client: billing_v1.CloudBillingClient, project_id: str,
                         billing_account) -> bool:
    """Link billing account to project and verify it's active."""
    project_name = f"projects/{project_id}"
    billing_account_name = billing_account.name
    display_name = billing_account.display_name

    print(f"   Linking '{display_name}' to project...")

    try:
        project_billing_info = billing_v1.ProjectBillingInfo(
            billing_account_name=billing_account_name
        )
        client.update_project_billing_info(
            name=project_name,
            project_billing_info=project_billing_info
        )
    except exceptions.PermissionDenied as e:
        print(f"   ❌ Permission denied. You may need 'Billing Account User' role.")
        print(f"      {e.message}")
        return False
    except Exception as e:
        print(f"   ❌ Failed to link: {e}")
        return False

    # Verify the link is active (can take a few seconds to propagate)
    print("   Verifying billing link...")
    max_retries = 6
    wait_seconds = 10

    for i in range(max_retries):
        try:
            info = client.get_project_billing_info(name=project_name)
            if info.billing_account_name == billing_account_name and info.billing_enabled:
                print(f"   ✓ Billing verified active")
                return True
        except Exception:
            pass

        if i < max_retries - 1:
            time.sleep(wait_seconds)

    print("   ⚠️  Could not verify billing link (may still be propagating)")
    return True  # Optimistically continue


def main():
    """Main billing enablement flow."""
    print("💳 Checking billing configuration...")

    # Get project ID
    project_id = get_project_id()
    print(f"   Project: {project_id}")

    # Initialize billing client
    billing_client = billing_v1.CloudBillingClient()

    # Check if billing is already enabled
    is_enabled, current_account = check_current_billing(billing_client, project_id)
    if is_enabled:
        print(f"   ✓ Billing already enabled")
        return 0

    print("   Billing not enabled. Searching for billing accounts...")

    # Try to get billing accounts
    accounts_result = get_billing_accounts(billing_client)

    # If API not ready, enable it and retry with backoff
    if accounts_result == "API_DISABLED_OR_PROPAGATING":
        if not enable_billing_api(project_id):
            return 1

        print("   Waiting for API to propagate...")
        max_retries = 5
        wait_seconds = 15

        for i in range(max_retries):
            print(f"   Retry {i + 1}/{max_retries} in {wait_seconds}s...")
            time.sleep(wait_seconds)
            accounts_result = get_billing_accounts(billing_client)
            if accounts_result != "API_DISABLED_OR_PROPAGATING":
                break
            wait_seconds = int(wait_seconds * 1.5)

    # If still no accounts, wait for potential credit propagation
    if isinstance(accounts_result, list) and not accounts_result:
        print("   No billing accounts found. Waiting for credit propagation...")
        print("   (This can take up to 2 minutes if you just claimed credits)")

        max_wait_retries = 6
        for i in range(max_wait_retries):
            print(f"   Waiting... ({i + 1}/{max_wait_retries})")
            time.sleep(20)
            accounts_result = get_billing_accounts(billing_client)
            if isinstance(accounts_result, list) and accounts_result:
                print("   ✓ Found billing accounts!")
                break

    # Handle final result
    if isinstance(accounts_result, list):
        if not accounts_result:
            print()
            print("╔═══════════════════════════════════════════════════════════════╗")
            print("║              ⚠️  BILLING ACCOUNT REQUIRED                      ║")
            print("╠═══════════════════════════════════════════════════════════════╣")
            print("║                                                               ║")
            print("║  No billing accounts found after waiting.                     ║")
            print("║                                                               ║")
            print("║  If you're at a workshop:                                     ║")
            print("║  • Make sure you've CLAIMED YOUR CREDIT from the organizer   ║")
            print("║  • Wait a minute for it to apply, then run setup again       ║")
            print("║                                                               ║")
            print("║  If you're self-learning:                                     ║")
            print("║  • Create a billing account (free tier available):            ║")
            print("║    https://console.cloud.google.com/billing/create            ║")
            print("║                                                               ║")
            print("╚═══════════════════════════════════════════════════════════════╝")
            return 1

        # Filter to open accounts only
        open_accounts = [acc for acc in accounts_result if acc.open]

        if not open_accounts:
            print("   ❌ Found billing accounts, but none are currently open/active.")
            return 1

        # If only one account, use it automatically
        if len(open_accounts) == 1:
            account = open_accounts[0]
            print(f"   Found: {account.display_name}")
            if link_billing_account(billing_client, project_id, account):
                print("✓ Billing configured successfully")
                return 0
            return 1

        # Multiple accounts - let user choose
        print(f"\n   Found {len(open_accounts)} billing accounts:")
        for i, acc in enumerate(open_accounts, 1):
            print(f"   {i}. {acc.display_name}")
        print()

        while True:
            try:
                choice = input(f"   Select account [1-{len(open_accounts)}]: ").strip()
                if not choice:
                    continue
                index = int(choice) - 1
                if 0 <= index < len(open_accounts):
                    break
                print(f"   Please enter 1-{len(open_accounts)}")
            except ValueError:
                print("   Please enter a number")

        account = open_accounts[index]
        if link_billing_account(billing_client, project_id, account):
            print("✓ Billing configured successfully")
            return 0
        return 1

    elif accounts_result == "API_DISABLED_OR_PROPAGATING":
        print("   ❌ Cloud Billing API did not become active.")
        print("   Please try again in a few minutes, or manually enable at:")
        print(f"   https://console.cloud.google.com/apis/library/cloudbilling.googleapis.com?project={project_id}")
        return 1

    elif accounts_result == "PERMISSION_DENIED":
        print("   ❌ You don't have permission to view billing accounts.")
        print("   Ask your organization admin for 'Billing Account User' role.")
        return 1

    else:
        print("   ❌ An unexpected error occurred.")
        return 1


if __name__ == "__main__":
    sys.exit(main())
