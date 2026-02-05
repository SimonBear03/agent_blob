from __future__ import annotations

import asyncio
import json
import os
import sys
import uuid
from dataclasses import dataclass
from typing import Dict, Optional

import websockets
from dotenv import load_dotenv

from agent_blob.clients.common.printer import Printer
from agent_blob import config


def _new_id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:12]}"


@dataclass
class RunBuffer:
    run_id: str
    status: str = "created"
    done: bool = False


async def _stdin_lines(queue: asyncio.Queue[str]):
    loop = asyncio.get_running_loop()
    while True:
        line = await loop.run_in_executor(None, sys.stdin.readline)
        if not line:
            await queue.put("__EOF__")
            return
        await queue.put(line.rstrip("\n"))


async def main() -> None:
    load_dotenv()

    host = config.gateway_host()
    port = config.gateway_port()
    url = f"ws://{host}:{port}/ws"

    device_id = config.cli_device_id()
    client_type = "cli"

    runs: Dict[str, RunBuffer] = {}
    pending_permissions: Dict[str, str] = {}  # request_id -> run_id
    pending_lock = asyncio.Lock()
    printer = Printer()

    stdin_q: asyncio.Queue[str] = asyncio.Queue()
    asyncio.create_task(_stdin_lines(stdin_q))

    async with websockets.connect(url) as ws:
        connect_id = _new_id("connect")
        await ws.send(
            json.dumps(
                {
                    "type": "req",
                    "id": connect_id,
                    "method": "connect",
                    "params": {"version": "2", "clientType": client_type, "deviceId": device_id},
                }
            )
        )

        async def send_run(text: str):
            req_id = _new_id("req")
            run_id = _new_id("run")
            runs[run_id] = RunBuffer(run_id=run_id)
            await ws.send(
                json.dumps(
                    {
                        "type": "req",
                        "id": req_id,
                        "method": "run.create",
                        "params": {"runId": run_id, "input": text},
                    }
                )
            )
            print(f"\n[{run_id}] queued")

        async def handle_event(msg: dict):
            event_type = msg.get("event")
            payload = msg.get("payload") or {}

            if event_type == "permission.request":
                request_id = payload.get("requestId", "")
                run_id = payload.get("runId", "")
                async with pending_lock:
                    pending_permissions[request_id] = run_id
                capability = payload.get("capability", "")
                preview = payload.get("preview", "")
                reason = payload.get("reason", "")
                print(f"\n[{run_id}] permission required: {capability}")
                if reason:
                    print(f"  reason: {reason}")
                if preview:
                    print(f"  preview: {preview}")
                print("Allow? [y/N] ", end="", flush=True)
                return

            if event_type in ("run.status", "run.log", "run.error", "run.final", "run.token", "run.tool_call", "run.tool_result"):
                run_id = payload.get("runId", "")
                if run_id and run_id not in runs:
                    runs[run_id] = RunBuffer(run_id=run_id)
                buf = runs.get(run_id)

                if event_type == "run.status" and buf:
                    buf.status = payload.get("status", buf.status)
                    printer.status(run_id, buf.status)
                elif event_type == "run.log":
                    printer.log(run_id, payload.get("message", ""))
                elif event_type == "run.error":
                    printer.error(run_id, payload.get("message", ""))
                    if buf:
                        buf.done = True
                elif event_type == "run.final":
                    if buf:
                        buf.done = True
                        printer.done(run_id)
                elif event_type == "run.token":
                    printer.token(run_id, payload.get("content", ""))
                elif event_type == "run.tool_call":
                    printer.log(run_id, f"tool_call: {payload.get('toolName','')} {payload.get('arguments',{})}")
                elif event_type == "run.tool_result":
                    printer.log(run_id, f"tool_result: {payload.get('toolName','')} {payload.get('ok', True)}")

        async def handle_response(msg: dict):
            if msg.get("ok") is False:
                print(f"\n[res] error: {msg.get('error')}")

        async def receiver():
            while True:
                raw = await ws.recv()
                msg = json.loads(raw)
                if msg.get("type") == "event":
                    await handle_event(msg)
                elif msg.get("type") == "res":
                    await handle_response(msg)

        async def sender():
            while True:
                line = await stdin_q.get()
                if line == "__EOF__":
                    return
                line = (line or "").strip()
                if not line:
                    continue

                async with pending_lock:
                    pending = list(pending_permissions.items())
                if pending:
                    request_id, run_id = pending[0]
                    decision = "allow" if line.lower() in ("y", "yes", "allow") else "deny"
                    async with pending_lock:
                        pending_permissions.pop(request_id, None)
                    await ws.send(
                        json.dumps(
                            {
                                "type": "req",
                                "id": _new_id("perm"),
                                "method": "permission.respond",
                                "params": {"requestId": request_id, "decision": decision, "remember": False},
                            }
                        )
                    )
                    print(f"\n[{run_id}] permission: {decision}")
                else:
                    await send_run(line)

        await asyncio.gather(receiver(), sender())
