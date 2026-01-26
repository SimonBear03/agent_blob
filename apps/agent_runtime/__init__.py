"""
Agent Runtime - Core agent intelligence layer.

This module contains the agent loop, tools, and database operations.
It's transport-agnostic and yields event streams.
"""
from .runtime import AgentRuntime, get_runtime, init_runtime

__version__ = "0.1.1"
__all__ = ["AgentRuntime", "get_runtime", "init_runtime"]
