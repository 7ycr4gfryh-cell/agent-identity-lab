"""
Secure Customer Service Agent

A customer service agent with enterprise security guardrails:
- Model Armor Guard for input/output sanitization (via agent-level callbacks)
- OneMCP BigQuery for customer data access
- Agent Identity for least-privilege access
"""

from .agent import root_agent, create_agent

__all__ = ["root_agent", "create_agent"]
