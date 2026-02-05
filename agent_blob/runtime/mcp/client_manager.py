from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Optional

from agent_blob.config import load_config


@dataclass(frozen=True)
class MCPServerConfig:
    name: str
    url: str
    transport: str = "streamable-http"  # streamable-http|ws|stdio (we implement streamable-http)


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
        Discover MCP tools from configured servers.

        Returns a list of dict tool descriptions:
          {server, name, description, inputSchema}
        """
        from agent_blob.runtime.mcp.http_client import MCPStreamableHttpClient

        out: List[Dict[str, Any]] = []
        for s in self._servers:
            if s.transport != "streamable-http":
                continue
            client = MCPStreamableHttpClient(base_url=s.url)
            try:
                tools = await client.tools_list()
                for t in tools:
                    out.append(
                        {
                            "server": s.name,
                            "name": t.name,
                            "description": t.description,
                            "inputSchema": t.input_schema,
                        }
                    )
            finally:
                await client.close()
        return out

    async def call_tool(self, *, server: str, name: str, arguments: Dict[str, Any]) -> Any:
        from agent_blob.runtime.mcp.http_client import MCPStreamableHttpClient

        cfg = {s.name: s for s in self._servers}
        s = cfg.get(server)
        if not s:
            raise RuntimeError(f"Unknown MCP server: {server}")
        if s.transport != "streamable-http":
            raise RuntimeError(f"Unsupported MCP transport: {s.transport}")
        client = MCPStreamableHttpClient(base_url=s.url)
        try:
            return await client.tools_call(name=name, arguments=arguments)
        finally:
            await client.close()
