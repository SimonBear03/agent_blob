"""
Tool registry for managing and executing agent tools.
"""
import json
from typing import Dict, Callable, Any, Optional
from pathlib import Path
import os


class ToolDefinition:
    """Definition of a tool that the agent can use."""
    
    def __init__(
        self,
        name: str,
        description: str,
        parameters: dict,
        executor: Callable,
        metadata: Optional[dict] = None
    ):
        self.name = name
        self.description = description
        self.parameters = parameters
        self.executor = executor
        self.metadata = metadata or {}
    
    def to_openai_function(self) -> dict:
        """Convert to OpenAI function calling format (v2.x)."""
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": self.parameters
            }
        }
    
    async def execute(self, **kwargs) -> Any:
        """Execute the tool with given parameters."""
        return await self.executor(**kwargs)


class ToolRegistry:
    """Registry for managing available tools."""
    
    def __init__(self):
        self._tools: Dict[str, ToolDefinition] = {}
    
    def register(self, tool: ToolDefinition):
        """Register a tool."""
        self._tools[tool.name] = tool
    
    def get(self, name: str) -> Optional[ToolDefinition]:
        """Get a tool by name."""
        return self._tools.get(name)
    
    def list_tools(self) -> list[ToolDefinition]:
        """List all registered tools."""
        return list(self._tools.values())
    
    def to_openai_functions(self) -> list[dict]:
        """Convert all tools to OpenAI function format."""
        return [tool.to_openai_function() for tool in self._tools.values()]
    
    async def execute_tool(self, name: str, parameters: dict) -> Any:
        """Execute a tool by name with parameters."""
        tool = self.get(name)
        if not tool:
            raise ValueError(f"Tool '{name}' not found in registry")
        
        return await tool.execute(**parameters)


# Global registry instance
_registry: Optional[ToolRegistry] = None


def get_registry() -> ToolRegistry:
    """Get the global tool registry."""
    global _registry
    if _registry is None:
        _registry = ToolRegistry()
        # Register default tools
        from tools import filesystem, memory_tools
        filesystem.register_tools(_registry)
        memory_tools.register_tools(_registry)
    return _registry


def init_registry() -> ToolRegistry:
    """Initialize a fresh registry."""
    global _registry
    _registry = ToolRegistry()
    return _registry
