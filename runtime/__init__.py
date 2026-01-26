"""
Agent Runtime - Core agent intelligence layer.

This module contains the agent loop, tools, and database operations.
It's transport-agnostic and yields event streams.
"""
from .runtime import AgentRuntime, get_runtime, init_runtime
from .processes import ProcessManager, get_process_manager
from .tools import ToolRegistry, get_registry

__version__ = "0.1.1"
__all__ = [
    "AgentRuntime", "get_runtime", "init_runtime",
    "ProcessManager", "get_process_manager",
    "ToolRegistry", "get_registry"
]
