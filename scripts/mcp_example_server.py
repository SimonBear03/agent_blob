#!/usr/bin/env python3
"""
Minimal MCP Streamable HTTP example server (for local testing).

Runs a JSON-RPC endpoint that supports:
- initialize
- tools/list
- tools/call
- prompts/list
- prompts/get

Start:
  python3 scripts/mcp_example_server.py --port 9000

Configure Agent Blob:
  Add to agent_blob.json:
    "mcp": { "servers": [ { "name": "example", "url": "http://127.0.0.1:9000/mcp", "transport": "streamable-http" } ] }
"""

from __future__ import annotations

import argparse
import time
import uuid
from typing import Any, Dict, Optional

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse


def _rpc_result(req_id: str, result: Any) -> Dict[str, Any]:
    return {"jsonrpc": "2.0", "id": req_id, "result": result}


def _rpc_error(req_id: str, code: int, message: str) -> Dict[str, Any]:
    return {"jsonrpc": "2.0", "id": req_id, "error": {"code": int(code), "message": str(message)}}


def create_app() -> FastAPI:
    app = FastAPI(title="Agent Blob MCP Example Server", version="0.1.0")
    session_id = f"sid_{uuid.uuid4().hex[:12]}"

    @app.get("/health")
    async def health():
        return {"ok": True}

    @app.post("/mcp")
    async def mcp(request: Request):
        try:
            payload = await request.json()
        except Exception:
            return JSONResponse(_rpc_error("unknown", -32700, "Parse error"), status_code=200)

        if not isinstance(payload, dict):
            return JSONResponse(_rpc_error("unknown", -32600, "Invalid Request"), status_code=200)

        req_id = str(payload.get("id") or "unknown")
        method = str(payload.get("method") or "")
        params = payload.get("params") or {}
        if params is not None and not isinstance(params, dict):
            params = {}

        if method == "initialize":
            res = _rpc_result(
                req_id,
                {
                    "protocolVersion": "2024-11-05",
                    "serverInfo": {"name": "agent_blob_mcp_example", "version": "0.1.0"},
                    "capabilities": {"tools": {}, "prompts": {}},
                    "sessionId": session_id,
                },
            )
            return JSONResponse(res, headers={"Mcp-Session-Id": session_id})

        if method == "tools/list":
            return JSONResponse(
                _rpc_result(
                    req_id,
                    {
                        "tools": [
                            {
                                "name": "example.echo",
                                "description": "Echo back the provided text.",
                                "inputSchema": {
                                    "type": "object",
                                    "properties": {"text": {"type": "string"}},
                                    "required": ["text"],
                                },
                            },
                            {
                                "name": "example.add",
                                "description": "Add two numbers.",
                                "inputSchema": {
                                    "type": "object",
                                    "properties": {"a": {"type": "number"}, "b": {"type": "number"}},
                                    "required": ["a", "b"],
                                },
                            },
                            {
                                "name": "example.time",
                                "description": "Return server time (unix seconds).",
                                "inputSchema": {"type": "object", "properties": {}},
                            },
                        ]
                    },
                )
            )

        if method == "tools/call":
            name = str(params.get("name") or "")
            arguments = params.get("arguments") or {}
            if not isinstance(arguments, dict):
                arguments = {}

            if name == "example.echo":
                text = str(arguments.get("text") or "")
                return JSONResponse(_rpc_result(req_id, {"content": [{"type": "text", "text": text}]}))
            if name == "example.add":
                try:
                    a = float(arguments.get("a"))
                    b = float(arguments.get("b"))
                except Exception:
                    return JSONResponse(_rpc_error(req_id, -32602, "Invalid params"), status_code=200)
                return JSONResponse(_rpc_result(req_id, {"content": [{"type": "text", "text": str(a + b)}]}))
            if name == "example.time":
                return JSONResponse(_rpc_result(req_id, {"content": [{"type": "text", "text": str(int(time.time()))}]}))

            return JSONResponse(_rpc_error(req_id, -32601, f"Unknown tool: {name}"), status_code=200)

        if method == "prompts/list":
            return JSONResponse(
                _rpc_result(
                    req_id,
                    {
                        "prompts": [
                            {
                                "name": "example.greeting",
                                "description": "A simple greeting prompt template.",
                                "arguments": [{"name": "name", "description": "Name to greet", "required": False}],
                            }
                        ]
                    },
                )
            )

        if method == "prompts/get":
            name = str(params.get("name") or "")
            arguments = params.get("arguments") or {}
            if not isinstance(arguments, dict):
                arguments = {}
            if name != "example.greeting":
                return JSONResponse(_rpc_error(req_id, -32601, f"Unknown prompt: {name}"), status_code=200)
            who = str(arguments.get("name") or "there")
            return JSONResponse(
                _rpc_result(
                    req_id,
                    {
                        "name": name,
                        "messages": [{"role": "system", "content": f"Say hello to {who}."}],
                    },
                )
            )

        return JSONResponse(_rpc_error(req_id, -32601, f"Unknown method: {method}"), status_code=200)

    return app


def main(argv: Optional[list[str]] = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=9000)
    args = parser.parse_args(argv)

    import uvicorn

    uvicorn.run(create_app(), host=args.host, port=args.port)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

