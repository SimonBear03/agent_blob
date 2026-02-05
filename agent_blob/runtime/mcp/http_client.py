from __future__ import annotations

import json
import time
from dataclasses import dataclass
from typing import Any, Dict, List, Optional
from uuid import uuid4


class MCPError(RuntimeError):
    pass


@dataclass
class MCPTool:
    name: str
    description: str
    input_schema: Dict[str, Any]


class MCPStreamableHttpClient:
    """
    Minimal MCP Streamable HTTP client.

    Implements enough of the draft spec to:
    - initialize session
    - tools/list
    - tools/call
    - prompts/list + prompts/get (returned as raw payload)

    References:
    - MCP architecture and primitives: tools/resources/prompts over a client-server protocol.
    """

    def __init__(self, *, base_url: str, timeout_s: float = 30.0):
        self.base_url = base_url.rstrip("/")
        self.timeout_s = float(timeout_s)
        self._session_id: Optional[str] = None

        try:
            import httpx  # type: ignore
        except Exception as e:
            raise MCPError("httpx is required for MCP Streamable HTTP") from e
        self._httpx = httpx

        self._client = httpx.AsyncClient(timeout=self.timeout_s)

    async def close(self) -> None:
        await self._client.aclose()

    async def _rpc(self, method: str, params: Optional[Dict[str, Any]] = None) -> Any:
        req_id = uuid4().hex
        body = {"jsonrpc": "2.0", "id": req_id, "method": method}
        if params is not None:
            body["params"] = params

        headers = {"Content-Type": "application/json"}
        if self._session_id:
            headers["Mcp-Session-Id"] = self._session_id

        resp = await self._client.post(self.base_url, headers=headers, json=body)
        if resp.status_code >= 400:
            raise MCPError(f"HTTP {resp.status_code}: {resp.text[:300]}")

        data = resp.json()
        if not isinstance(data, dict):
            raise MCPError("Invalid JSON-RPC response")
        if data.get("error"):
            raise MCPError(str(data["error"]))
        return data.get("result")

    async def initialize(self) -> None:
        """
        Initialize and store session id, if returned via headers.
        """
        # The spec uses initialize + initialized; for our minimal client we just call initialize.
        headers = {"Content-Type": "application/json"}
        body = {
            "jsonrpc": "2.0",
            "id": uuid4().hex,
            "method": "initialize",
            "params": {
                "protocolVersion": "2024-11-05",
                "capabilities": {},
                "clientInfo": {"name": "agent_blob", "version": "2.0.0"},
            },
        }
        resp = await self._client.post(self.base_url, headers=headers, json=body)
        if resp.status_code >= 400:
            raise MCPError(f"HTTP {resp.status_code}: {resp.text[:300]}")
        sid = resp.headers.get("Mcp-Session-Id") or resp.headers.get("mcp-session-id")
        if sid:
            self._session_id = sid
        # Some servers return session id in result; keep it if present.
        try:
            result = resp.json().get("result")  # type: ignore
            if isinstance(result, dict) and result.get("sessionId") and not self._session_id:
                self._session_id = str(result["sessionId"])
        except Exception:
            pass

    async def tools_list(self) -> List[MCPTool]:
        if not self._session_id:
            await self.initialize()
        result = await self._rpc("tools/list", params={})
        tools = result.get("tools") if isinstance(result, dict) else None
        out: List[MCPTool] = []
        if isinstance(tools, list):
            for t in tools:
                if not isinstance(t, dict):
                    continue
                out.append(
                    MCPTool(
                        name=str(t.get("name", "") or ""),
                        description=str(t.get("description", "") or ""),
                        input_schema=dict(t.get("inputSchema") or {}),
                    )
                )
        return out

    async def tools_call(self, *, name: str, arguments: Dict[str, Any]) -> Any:
        if not self._session_id:
            await self.initialize()
        return await self._rpc("tools/call", params={"name": name, "arguments": arguments})

    async def prompts_list(self) -> Any:
        if not self._session_id:
            await self.initialize()
        return await self._rpc("prompts/list", params={})

    async def prompts_get(self, *, name: str, arguments: Optional[Dict[str, Any]] = None) -> Any:
        if not self._session_id:
            await self.initialize()
        params: Dict[str, Any] = {"name": name}
        if arguments:
            params["arguments"] = arguments
        return await self._rpc("prompts/get", params=params)

