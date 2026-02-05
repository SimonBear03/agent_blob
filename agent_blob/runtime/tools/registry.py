from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Awaitable, Callable, Dict, List


ToolExecutor = Callable[[Dict[str, Any]], Awaitable[Any]]


@dataclass(frozen=True)
class ToolDefinition:
    """
    name: OpenAI function name (must be simple, no dots)
    capability: policy capability string (e.g. "shell.run")
    """

    name: str
    capability: str
    description: str
    parameters: Dict[str, Any]  # JSON schema
    executor: ToolExecutor

    def to_openai_tool(self) -> Dict[str, Any]:
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": self.parameters,
            },
        }


class ToolRegistry:
    def __init__(self, tools: List[ToolDefinition]):
        self._tools = {t.name: t for t in tools}

    def to_openai_tools(self) -> List[Dict[str, Any]]:
        return [t.to_openai_tool() for t in self._tools.values()]

    def get(self, name: str) -> ToolDefinition:
        if name not in self._tools:
            raise KeyError(f"Tool not found: {name}")
        return self._tools[name]

