"""
=============================================================================
Model Armor Guard for ADK
=============================================================================
This module provides Model Armor integration via agent-level callbacks.

This module provides:
- ModelArmorGuard: A class that creates callback functions for LlmAgent
- create_model_armor_guard(): Factory to get a configured guard instance

Security protections:
- Prompt injection & jailbreak detection
- Sensitive data protection (SSN, credit cards, API keys)
- Harmful content filtering (harassment, hate speech, dangerous)
- Malicious URL detection

=============================================================================
YOUR TASK: Implement the placeholder sections marked with TODO
=============================================================================
"""

import os
from typing import Optional

from google.adk.agents.callback_context import CallbackContext
from google.adk.models.llm_request import LlmRequest
from google.adk.models.llm_response import LlmResponse
from google.genai import types

# Model Armor imports
from google.cloud import modelarmor_v1
from google.api_core.client_options import ClientOptions


class ModelArmorGuard:
    """
    Model Armor security guard that provides callbacks for LlmAgent.

    Unlike plugins (which require Runner registration and don't work with
    `adk web`), this class provides standalone callback functions that can
    be passed directly to LlmAgent's before_model_callback and after_model_callback.

    Usage:
        guard = ModelArmorGuard(template_name="projects/.../templates/...")

        agent = LlmAgent(
            model="gemini-2.5-flash",
            before_model_callback=guard.before_model_callback,
            after_model_callback=guard.after_model_callback,
        )
    """

    def __init__(
            self,
            template_name: str,
            location: str = "us-central1",
            block_on_match: bool = True,
    ):
        """
        Initialize the Model Armor Guard.

        Args:
            template_name: Full resource name of the Model Armor template
                          (e.g., "projects/my-project/locations/us-central1/templates/my-template")
            location: Google Cloud region where Model Armor is deployed
            block_on_match: If True, block requests when threats detected.
                           If False, log warnings but allow through.
        """
        self.template_name = template_name
        self.location = location
        self.block_on_match = block_on_match

        # =================================================================
        # TODO 1: Initialize the Model Armor client
        # =================================================================
        # Create a ModelArmorClient using the REST transport
        # =================================================================

        self.client = None  # PLACEHOLDER - Replace with your implementation

        print(f"[ModelArmorGuard] ✅ Initialized with template: {template_name}")

    def _get_matched_filters(self, result) -> list[str]:
        """
        Extract filter names that detected threats from a sanitization result.

        Args:
            result: SanitizeUserPromptResponse or SanitizeModelResponseResponse

        Returns:
            List of filter names that matched (e.g., ['pi_and_jailbreak', 'sdp'])
        """
        matched_filters = []

        if result is None:
            return matched_filters

        # Navigate to filter_results
        try:
            filter_results = dict(result.sanitization_result.filter_results)
        except (AttributeError, TypeError):
            return matched_filters

        # Mapping of filter names to their corresponding result attribute names
        filter_attr_mapping = {
            'csam': 'csam_filter_filter_result',
            'malicious_uris': 'malicious_uri_filter_result',
            'pi_and_jailbreak': 'pi_and_jailbreak_filter_result',
            'rai': 'rai_filter_result',
            'sdp': 'sdp_filter_result',
            'virus_scan': 'virus_scan_filter_result'
        }

        for filter_name, filter_obj in filter_results.items():
            # Get the appropriate attribute name for this filter
            attr_name = filter_attr_mapping.get(filter_name)

            if not attr_name:
                # Try to construct the attribute name if not in mapping
                if filter_name == 'malicious_uris':
                    attr_name = 'malicious_uri_filter_result'
                else:
                    attr_name = f'{filter_name}_filter_result'

            # Get the actual filter result
            if hasattr(filter_obj, attr_name):
                filter_result = getattr(filter_obj, attr_name)

                # Special handling for SDP (has inspect_result wrapper)
                if filter_name == 'sdp' and hasattr(filter_result, 'inspect_result'):
                    if hasattr(filter_result.inspect_result, 'match_state'):
                        if filter_result.inspect_result.match_state.name == 'MATCH_FOUND':
                            matched_filters.append('sdp')

                # Special handling for RAI (has subcategories)
                elif filter_name == 'rai':
                    # Check main RAI match state
                    if hasattr(filter_result, 'match_state'):
                        if filter_result.match_state.name == 'MATCH_FOUND':
                            matched_filters.append('rai')

                    # Check RAI subcategories
                    if hasattr(filter_result, 'rai_filter_type_results'):
                        for sub_result in filter_result.rai_filter_type_results:
                            if hasattr(sub_result, 'key') and hasattr(sub_result, 'value'):
                                if hasattr(sub_result.value, 'match_state'):
                                    if sub_result.value.match_state.name == 'MATCH_FOUND':
                                        matched_filters.append(f'rai:{sub_result.key}')

                # Standard filters (pi_and_jailbreak, malicious_uris, etc.)
                else:
                    if hasattr(filter_result, 'match_state'):
                        if filter_result.match_state.name == 'MATCH_FOUND':
                            matched_filters.append(filter_name)

        return matched_filters

    def _extract_user_text(self, llm_request: LlmRequest) -> str:
        """Extract the user's text from the LLM request."""
        try:
            if llm_request.contents:
                for content in reversed(llm_request.contents):
                    if content.role == "user":
                        for part in content.parts:
                            if hasattr(part, 'text') and part.text:
                                return part.text
        except Exception as e:
            print(f"[ModelArmorGuard] Error extracting user text: {e}")
        return ""

    def _extract_model_text(self, llm_response: LlmResponse) -> str:
        """Extract the model's text from the LLM response."""
        try:
            if llm_response.content and llm_response.content.parts:
                for part in llm_response.content.parts:
                    if hasattr(part, 'text') and part.text:
                        return part.text
        except Exception as e:
            print(f"[ModelArmorGuard] Error extracting model text: {e}")
        return ""

    async def before_model_callback(
            self,
            callback_context: CallbackContext,
            llm_request: LlmRequest,
    ) -> Optional[LlmResponse]:
        """
        Callback called BEFORE the LLM processes the request.

        This sanitizes user prompts to detect:
        - Prompt injection attacks
        - Sensitive data in user input
        - Harmful content

        Args:
            callback_context: Context with session state and invocation info
            llm_request: The request about to be sent to the LLM

        Returns:
            None: Allow the request to proceed to the LLM
            LlmResponse: Block the request and return this response instead
        """
        # =================================================================
        # TODO 2: Extract user text from the request
        # =================================================================
        # Use self._extract_user_text() to get the user's message
        # If empty, return None to allow the request through
        # =================================================================

        user_text = ""  # PLACEHOLDER - Replace with your implementation

        print(f"[ModelArmorGuard] 🔍 Screening user prompt: '{user_text[:80]}...'")

        try:
            # =================================================================
            # TODO 3: Call Model Armor to sanitize the user prompt
            # =================================================================
            # Create a SanitizeUserPromptRequest and call the API
            # =================================================================

            result = None  # PLACEHOLDER - Replace with your implementation

            # =================================================================
            # TODO 4: Check for matched filters and block if needed
            # =================================================================
            # Use self._get_matched_filters(result) to check for threats
            # If threats found and self.block_on_match is True:
            #   - Log the blocked filters
            #   - Return an LlmResponse with a user-friendly message
            # =================================================================

            pass  # PLACEHOLDER - Replace with your implementation

            print(f"[ModelArmorGuard] ✅ User prompt passed security screening")

        except Exception as e:
            print(f"[ModelArmorGuard] ⚠️ Error during prompt sanitization: {e}")
            # On error, allow request through but log the issue

        return None

    async def after_model_callback(
            self,
            callback_context: CallbackContext,
            llm_response: LlmResponse,
    ) -> Optional[LlmResponse]:
        """
        Callback called AFTER the LLM generates a response.

        This sanitizes model outputs to detect:
        - Accidentally leaked sensitive data
        - Harmful content in model response
        - Malicious URLs in response

        Args:
            callback_context: Context with session state and invocation info
            llm_response: The response from the LLM

        Returns:
            None: Allow the response to return to the user
            LlmResponse: Replace the response with this sanitized version
        """
        # =================================================================
        # TODO 5: Extract model text from the response
        # =================================================================
        # Use self._extract_model_text() to get the model's response
        # If empty, return None to allow the response through
        # =================================================================

        model_text = ""  # PLACEHOLDER - Replace with your implementation

        print(f"[ModelArmorGuard] 🔍 Screening model response: '{model_text[:80]}...'")

        try:
            # =================================================================
            # TODO 6: Call Model Armor to sanitize the model response
            # =================================================================
            # Create a SanitizeModelResponseRequest and call the API
            # =================================================================

            result = None  # PLACEHOLDER - Replace with your implementation

            # =================================================================
            # TODO 7: Check for matched filters and sanitize if needed
            # =================================================================
            # Similar to TODO 4, but for model responses
            # If threats found, return a sanitized response
            # =================================================================

            pass  # PLACEHOLDER - Replace with your implementation

            print(f"[ModelArmorGuard] ✅ Model response passed security screening")

        except Exception as e:
            print(f"[ModelArmorGuard] ⚠️ Error during response sanitization: {e}")

        return None


# =============================================================================
# Factory function for easy guard creation
# =============================================================================

def create_model_armor_guard(
        project_id: str = None,
        location: str = None,
        template_name: str = None,
) -> ModelArmorGuard:
    """
    Create a ModelArmorGuard with configuration from environment variables.

    Environment variables:
        GOOGLE_CLOUD_PROJECT: GCP project ID
        GOOGLE_CLOUD_LOCATION: Region (default: us-central1)
        TEMPLATE_NAME: Full Model Armor template resource name

    Returns:
        Configured ModelArmorGuard instance
    """
    project_id = project_id or os.environ.get("GOOGLE_CLOUD_PROJECT") or os.environ.get("PROJECT_ID")
    location = location or os.environ.get("GOOGLE_CLOUD_LOCATION") or os.environ.get("LOCATION", "us-central1")
    template_name = template_name or os.environ.get("TEMPLATE_NAME")

    if not template_name:
        raise ValueError(
            "TEMPLATE_NAME environment variable not set. "
            "Run setup/create_template.py first."
        )

    return ModelArmorGuard(
        template_name=template_name,
        location=location,
        block_on_match=True,
    )
