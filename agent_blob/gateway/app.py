import asyncio
import logging
import os
import time
from dataclasses import dataclass
from typing import Any, Dict
from uuid import uuid4

from dotenv import load_dotenv
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware

from agent_blob.protocol import EventType, create_event, create_response
from agent_blob.policy.policy import Policy
from agent_blob.runtime.runtime import Runtime
from agent_blob import config

load_dotenv()

logger = logging.getLogger("agent_blob.gateway")
logging.basicConfig(level=logging.INFO)


@dataclass
class Client:
    websocket: WebSocket
    client_type: str
    device_id: str


class Gateway:
    def __init__(self):
        self.clients: Dict[WebSocket, Client] = {}
        self.runtime = Runtime()
        self.policy = Policy.load()
        self._permission_waiters: Dict[str, asyncio.Future[str]] = {}
        self._seq = 0
        self._supervisor_task: asyncio.Task | None = None

    async def startup(self):
        await self.runtime.startup()
        self._supervisor_task = asyncio.create_task(self._supervisor_loop())

    def _next_seq(self) -> int:
        self._seq += 1
        return self._seq

    async def _send_event(self, websocket: WebSocket, event: dict):
        if event.get("type") == "event" and event.get("seq") is None:
            event["seq"] = self._next_seq()
        await websocket.send_json(event)

    async def _broadcast_event(self, event: dict):
        for ws in list(self.clients.keys()):
            try:
                await self._send_event(ws, event.copy())
            except Exception:
                self.clients.pop(ws, None)

    async def _supervisor_loop(self):
        interval_s = config.supervisor_interval_s()
        debug_ticks = config.supervisor_debug()
        last_active_count: int | None = None
        last_maintenance_s: float = 0.0
        maintenance_interval_s = config.maintenance_interval_s()
        while True:
            try:
                tasks = await self.runtime.tasks.list_tasks()
                now = time.time()
                window_s = config.tasks_attach_window_s()
                always_active = {"running", "waiting_permission", "waiting_user"}
                active = []
                for t in tasks:
                    status = str(t.get("status") or "")
                    if status in ("done", "cancelled", "failed"):
                        continue
                    updated = float(t.get("updated_at", 0) or 0)
                    if status in always_active or (now - updated) <= window_s:
                        active.append(t)
                active_count = len(active)
                should_emit = debug_ticks or (last_active_count is None) or (active_count != last_active_count)
                if should_emit:
                    msg = f"supervisor: active_tasks={active_count}"
                    await self._broadcast_event(create_event(EventType.RUN_LOG, {"runId": "supervisor", "message": msg}))
                last_active_count = active_count

                now = asyncio.get_running_loop().time()
                if now - last_maintenance_s >= maintenance_interval_s:
                    last_maintenance_s = now
                    stats = await self.runtime.maintenance()
                    removed = ((stats.get("tasks") or {}).get("removed")) if isinstance(stats, dict) else 0
                    closed = ((stats.get("tasks_autoclosed") or {}).get("closed")) if isinstance(stats, dict) else 0
                    mem_added = stats.get("memory_added") if isinstance(stats, dict) else 0
                    emb = stats.get("embeddings_updated") if isinstance(stats, dict) else 0
                    if debug_ticks or removed or closed or mem_added or emb:
                        await self._broadcast_event(
                            create_event(
                                EventType.RUN_LOG,
                                {
                                    "runId": "supervisor",
                                    "message": f"maintenance: tasks_autoclosed={closed} tasks_removed={removed} memory_added={mem_added} embeddings_updated={emb}",
                                },
                            )
                        )
            except Exception as e:
                await self._broadcast_event(create_event(EventType.RUN_LOG, {"runId": "supervisor", "message": f"supervisor error: {e}"}))
            await asyncio.sleep(interval_s)

    async def ask_permission(
        self,
        websocket: WebSocket,
        *,
        run_id: str,
        capability: str,
        preview: str,
        reason: str,
    ) -> str:
        request_id = f"perm_{uuid4().hex[:12]}"
        fut: asyncio.Future[str] = asyncio.get_running_loop().create_future()
        self._permission_waiters[request_id] = fut

        await self._send_event(
            websocket,
            create_event(
                EventType.PERMISSION_REQUEST,
                {
                    "requestId": request_id,
                    "runId": run_id,
                    "capability": capability,
                    "preview": preview,
                    "reason": reason,
                },
            ),
        )
        try:
            return await fut
        finally:
            self._permission_waiters.pop(request_id, None)

    async def handle_permission_respond(self, websocket: WebSocket, req: dict):
        params = (req.get("params") or {})
        request_id = params.get("requestId", "")
        decision = params.get("decision", "deny")
        fut = self._permission_waiters.get(request_id)
        if fut and not fut.done():
            fut.set_result(decision)
            await websocket.send_json(create_response(req.get("id", "unknown"), ok=True, payload={"requestId": request_id}))
            return
        await websocket.send_json(create_response(req.get("id", "unknown"), ok=False, error="Unknown or expired permission request"))

    async def handle_run_create(self, websocket: WebSocket, req: dict):
        params = req.get("params") or {}
        run_id = params.get("runId") or f"run_{uuid4().hex[:12]}"
        user_input = params.get("input", "")

        await websocket.send_json(create_response(req.get("id", "unknown"), ok=True, payload={"runId": run_id, "status": "accepted"}))

        async def _runner():
            await self._send_event(websocket, create_event(EventType.RUN_STATUS, {"runId": run_id, "status": "running"}))
            try:
                async for ev in self.runtime.run(
                    run_id=run_id,
                    user_input=user_input,
                    policy=self.policy,
                    ask_permission=lambda **kwargs: self.ask_permission(websocket, **kwargs),
                ):
                    await self._send_event(websocket, ev)
            except Exception as e:
                await self._send_event(
                    websocket,
                    create_event(EventType.RUN_ERROR, {"runId": run_id, "message": str(e)}),
                )

        asyncio.create_task(_runner())


def create_app() -> FastAPI:
    gateway = Gateway()
    app = FastAPI(title="Agent Blob Gateway", version="2.0.0")

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.on_event("startup")
    async def _startup():
        await gateway.startup()

    @app.get("/health")
    async def health():
        return {"ok": True, "version": "2.0.0"}

    @app.websocket("/ws")
    async def ws_endpoint(websocket: WebSocket):
        await websocket.accept()
        try:
            # handshake
            req = await websocket.receive_json()
            if not _is_req(req):
                await websocket.send_json(create_response("unknown", ok=False, error="Invalid request"))
                await websocket.close()
                return
            if req.get("method") != "connect":
                await websocket.send_json(create_response(req.get("id", "unknown"), ok=False, error="First frame must be connect"))
                await websocket.close()
                return
            version = (req.get("params") or {}).get("version")
            if str(version) != "2":
                await websocket.send_json(create_response(req.get("id", "unknown"), ok=False, error="Unsupported protocol version"))
                await websocket.close()
                return
            client_type = (req.get("params") or {}).get("clientType", "unknown")
            device_id = (req.get("params") or {}).get("deviceId", "unknown")
            gateway.clients[websocket] = Client(websocket=websocket, client_type=client_type, device_id=device_id)
            await websocket.send_json(
                create_response(
                    req.get("id", "unknown"),
                    ok=True,
                    payload={"gatewayVersion": "2.0.0", "supportedMethods": ["run.create", "run.cancel", "permission.respond"]},
                )
            )

            # main loop
            while True:
                req = await websocket.receive_json()
                if not _is_req(req):
                    await websocket.send_json(create_response("unknown", ok=False, error="Invalid request"))
                    continue
                method = req.get("method")
                if method == "permission.respond":
                    await gateway.handle_permission_respond(websocket, req)
                elif method == "run.create":
                    await gateway.handle_run_create(websocket, req)
                else:
                    await websocket.send_json(create_response(req.get("id", "unknown"), ok=False, error=f"Unknown method: {method}"))
        except WebSocketDisconnect:
            pass
        finally:
            gateway.clients.pop(websocket, None)

    return app


def _is_req(v: Any) -> bool:
    return isinstance(v, dict) and v.get("type") == "req" and isinstance(v.get("id"), str) and isinstance(v.get("method"), str)
