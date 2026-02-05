from __future__ import annotations

import re
from typing import Any, Dict, List, Optional, Tuple

from agent_blob.runtime.capabilities.provider import CapabilityProvider
from agent_blob.runtime.mcp import MCPClientManager
from agent_blob.runtime.tools.registry import ToolDefinition


def _safe_name(s: str) -> str:
    s = re.sub(r"[^a-zA-Z0-9_]+", "_", s.strip())
    s = re.sub(r"_+", "_", s).strip("_")
    return s or "tool"


class MCPProvider:
    name = "mcp"

    def __init__(self):
        self.mgr = MCPClientManager()
        self._tool_cache: List[Dict[str, Any]] | None = None

    async def _ensure_cache(self) -> List[Dict[str, Any]]:
        if self._tool_cache is None:
            self._tool_cache = await self.mgr.list_tools()
        return self._tool_cache

    def tools(self) -> List[ToolDefinition]:
        # We can't do async discovery at construction time. Provide a lightweight "mcp_refresh" tool,
        # and expose MCP tools lazily at call-time via a generic dispatcher tool.
        async def _mcp_refresh(args: Dict[str, Any]) -> Any:
            self._tool_cache = await self.mgr.list_tools()
            return {"ok": True, "tools": self._tool_cache}

        async def _mcp_list(args: Dict[str, Any]) -> Any:
            if self._tool_cache is None:
                self._tool_cache = await self.mgr.list_tools()
            return {"ok": True, "tools": self._tool_cache}

        async def _mcp_call(args: Dict[str, Any]) -> Any:
            server = str(args.get("server", "") or "").strip()
            name = str(args.get("name", "") or "").strip()
            arguments = args.get("arguments") or {}
            if not isinstance(arguments, dict):
                arguments = {}
            return await self.mgr.call_tool(server=server, name=name, arguments=arguments)

        return [
            ToolDefinition(
                name="mcp_list_tools",
                capability="mcp.list",
                description="List tools from configured MCP servers.",
                parameters={"type": "object", "properties": {}},
                executor=_mcp_list,
            ),
            ToolDefinition(
                name="mcp_refresh",
                capability="mcp.refresh",
                description="Refresh MCP tool list from configured servers.",
                parameters={"type": "object", "properties": {}},
                executor=_mcp_refresh,
            ),
            ToolDefinition(
                name="mcp_call",
                capability="mcp.call",
                description="Call a tool on a configured MCP server (generic).",
                parameters={
                    "type": "object",
                    "properties": {
                        "server": {"type": "string", "description": "MCP server name"},
                        "name": {"type": "string", "description": "Tool name"},
                        "arguments": {"type": "object", "description": "Tool arguments (must be provided; use mcp_list_tools to see required fields)"},
                    },
                    "required": ["server", "name", "arguments"],
                },
                executor=_mcp_call,
            ),
        ]

    def system_instructions(self) -> Optional[str]:
        servers = self.mgr.list_servers()
        if not servers:
            return None
        return (
            "MCP is enabled. Configured servers:\n"
            + "\n".join([f"- {s['name']}: {s['url']} ({s['transport']})" for s in servers])
            + "\nUse mcp_list_tools (or mcp_refresh) to discover tool schemas, then call them via mcp_call.\n"
            + "When calling mcp_call you MUST include an 'arguments' object that matches the tool's inputSchema.\n"
            + "Always use the exact tool name from mcp_list_tools (e.g. 'demo.add', not 'add').\n"
        )
