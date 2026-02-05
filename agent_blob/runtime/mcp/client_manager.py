from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Optional

from agent_blob.config import load_config


@dataclass(frozen=True)
class MCPServerConfig:
    name: str
    url: str
    transport: str = "ws"  # placeholder: ws/http/stdin


class MCPClientManager:
    """
    Minimal scaffold for MCP integration.

    V1 goal: keep an explicit boundary so the runtime can later expose MCP tools
    alongside local tools, without coupling the agent loop to a specific MCP lib.
    """

    def __init__(self):
        self._servers = self._load_servers()

    def _load_servers(self) -> List[MCPServerConfig]:
        cfg = load_config()
        mcp = (cfg.get("mcp") or {}) if isinstance(cfg, dict) else {}
        servers = mcp.get("servers") if isinstance(mcp, dict) else None
        out: List[MCPServerConfig] = []
        if isinstance(servers, list):
            for s in servers:
                if not isinstance(s, dict):
                    continue
                name = str(s.get("name", "") or "").strip()
                url = str(s.get("url", "") or "").strip()
                transport = str(s.get("transport", "ws") or "ws").strip()
                if name and url:
                    out.append(MCPServerConfig(name=name, url=url, transport=transport))
        return out

    def list_servers(self) -> List[Dict[str, str]]:
        return [{"name": s.name, "url": s.url, "transport": s.transport} for s in self._servers]

    async def list_tools(self) -> List[Dict[str, Any]]:
        """
        Placeholder for future: discover MCP tools from configured servers.

        Returns a list of tool definitions that can be injected into the ToolRegistry.
        """
        return []

