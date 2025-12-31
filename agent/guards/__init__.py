"""
Guards module for security callbacks.

This module provides agent-level callbacks for security features.
Unlike plugins (which don't work with `adk web`), guards use
agent-level callbacks that work in all environments.
"""

from .model_armor_guard import ModelArmorGuard, create_model_armor_guard

__all__ = ["ModelArmorGuard", "create_model_armor_guard"]
