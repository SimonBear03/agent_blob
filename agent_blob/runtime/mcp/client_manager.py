from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Optional

from agent_blob.config import load_config_uncached
from agent_blob.runtime.mcp.http_client import MCPStreamableHttpClient


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
        self._tools_cache: Dict[str, List[Dict[str, Any]]] = {}

    def _load_servers(self) -> List[MCPServerConfig]:
        cfg = load_config_uncached()
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

    def reload(self) -> None:
        """
        Reload server configuration from agent_blob.json.
        """
        self._servers = self._load_servers()
        self._tools_cache = {}

    def list_servers(self) -> List[Dict[str, str]]:
        # Keep server config fresh even if agent_blob.json changes while running.
        self.reload()
        return [{"name": s.name, "url": s.url, "transport": s.transport} for s in self._servers]

    async def list_tools(self) -> List[Dict[str, Any]]:
        """
        Discover MCP tools from configured servers.

        Returns a list of dict tool descriptions:
          {server, name, description, inputSchema}
        """
        # Keep server config fresh even if agent_blob.json changes while running.
        self.reload()

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
        # Cache per-server
        by_server: Dict[str, List[Dict[str, Any]]] = {}
        for t in out:
            by_server.setdefault(str(t.get("server")), []).append(t)
        for k, v in by_server.items():
            self._tools_cache[k] = v
        return out

    async def call_tool(self, *, server: str, name: str, arguments: Dict[str, Any]) -> Any:
        # Keep server config fresh even if agent_blob.json changes while running.
        self.reload()
        cfg = {s.name: s for s in self._servers}
        s = cfg.get(server)
        if not s:
            raise RuntimeError(f"Unknown MCP server: {server}")
        if s.transport != "streamable-http":
            raise RuntimeError(f"Unsupported MCP transport: {s.transport}")

        # Resolve tool name: prefer exact; else allow unique suffix matches like "add" -> "quant.add".
        resolved = await self._resolve_tool_name(server=server, name=name)

        client = MCPStreamableHttpClient(base_url=s.url)
        try:
            return await client.tools_call(name=resolved, arguments=arguments)
        finally:
            await client.close()

    async def list_prompts(self) -> List[Dict[str, Any]]:
        """
        List prompts from configured MCP servers.

        Returns items like:
          {server, name, description, arguments?}
        """
        self.reload()
        out: List[Dict[str, Any]] = []
        for s in self._servers:
            if s.transport != "streamable-http":
                continue
            client = MCPStreamableHttpClient(base_url=s.url)
            try:
                result = await client.prompts_list()
                prompts = result.get("prompts") if isinstance(result, dict) else None
                if isinstance(prompts, list):
                    for p in prompts:
                        if not isinstance(p, dict):
                            continue
                        out.append({"server": s.name, **p})
            finally:
                await client.close()
        return out

    async def get_prompt(self, *, server: str, name: str, arguments: Optional[Dict[str, Any]] = None) -> Any:
        self.reload()
        cfg = {s.name: s for s in self._servers}
        s = cfg.get(server)
        if not s:
            raise RuntimeError(f"Unknown MCP server: {server}")
        if s.transport != "streamable-http":
            raise RuntimeError(f"Unsupported MCP transport: {s.transport}")
        client = MCPStreamableHttpClient(base_url=s.url)
        try:
            return await client.prompts_get(name=name, arguments=arguments)
        finally:
            await client.close()

    async def _resolve_tool_name(self, *, server: str, name: str) -> str:
        raw = str(name or "").strip()
        if not raw:
            raise RuntimeError("Missing MCP tool name")

        tools = self._tools_cache.get(server)
        if tools is None:
            # Populate cache for this server only.
            all_tools = await self.list_tools()
            tools = [t for t in all_tools if t.get("server") == server]
            self._tools_cache[server] = tools

        names = [str(t.get("name", "")) for t in (tools or []) if isinstance(t, dict)]
        if raw in names:
            return raw

        # If no dot, try prefixing with server name.
        if "." not in raw:
            pref = f"{server}.{raw}"
            if pref in names:
                return pref

        # Unique suffix match (e.g. "add" -> "* .add")
        suffix = f".{raw}" if not raw.startswith(".") else raw
        matches = [n for n in names if n.endswith(suffix)]
        if len(matches) == 1:
            return matches[0]

        if matches:
            raise RuntimeError(f"Ambiguous MCP tool name '{raw}'. Matches: {matches[:5]}")
        raise RuntimeError(f"Unknown MCP tool name '{raw}'. Known tools: {names[:10]}")
