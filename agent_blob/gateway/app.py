import asyncio
import logging
import os
import time
from dataclasses import dataclass
from typing import Any, Awaitable, Callable, Dict
from uuid import uuid4

from dotenv import load_dotenv
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware

from agent_blob.protocol import EventType, create_event, create_response
from agent_blob.policy.policy import Policy
from agent_blob.runtime.runtime import Runtime
from agent_blob import config
from agent_blob.frontends.adapters.manager import start_enabled_adapters

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
        # Offline-safe permission requests (primarily for scheduled/background runs).
        # request_id -> {"runId": str, "event": dict}
        self._pending_permission_events: Dict[str, Dict[str, Any]] = {}
        self._seq = 0
        self._supervisor_task: asyncio.Task | None = None
        self._adapter_tasks: list[asyncio.Task] = []

    async def startup(self):
        await self.runtime.startup()
        self._supervisor_task = asyncio.create_task(self._supervisor_loop())
        self._adapter_tasks = await start_enabled_adapters(gateway=self)

    def _next_seq(self) -> int:
        self._seq += 1
        return self._seq

    def _with_seq(self, event: dict) -> dict:
        out = dict(event)
        if out.get("type") == "event" and out.get("seq") is None:
            out["seq"] = self._next_seq()
        return out

    async def _send_event(self, websocket: WebSocket, event: dict):
        payload = self._with_seq(event)
        try:
            await websocket.send_json(payload)
        except Exception as e:
            # Client likely disconnected; ensure we stop treating it as active.
            self.clients.pop(websocket, None)
            raise ConnectionError("WebSocket send failed") from e

    async def _broadcast_event(self, event: dict):
        for ws in list(self.clients.keys()):
            try:
                await self._send_event(ws, event)
            except Exception:
                self.clients.pop(ws, None)

    def _ws_sender(self, websocket: WebSocket) -> Callable[[dict], Awaitable[None]]:
        async def _send(ev: dict) -> None:
            await self._send_event(websocket, ev)
        return _send

    async def _ask_permission_broadcast(
        self,
        *,
        run_id: str,
        capability: str,
        preview: str,
        reason: str,
    ) -> str:
        """
        Permission prompt that any connected client can answer.
        Used for background/scheduled runs.
        """
        request_id = f"perm_{uuid4().hex[:12]}"
        fut: asyncio.Future[str] = asyncio.get_running_loop().create_future()
        self._permission_waiters[request_id] = fut
        payload = {
            "requestId": request_id,
            "runId": run_id,
            "capability": capability,
            "preview": preview,
            "reason": reason,
        }
        ev = create_event(EventType.PERMISSION_REQUEST, payload)
        self._pending_permission_events[request_id] = {"runId": run_id, "event": ev}

        # If no clients are connected, keep it queued until someone connects.
        if self.clients:
            await self._broadcast_event(create_event(EventType.RUN_STATUS, {"runId": run_id, "status": "waiting_permission"}))
            await self._broadcast_event(ev)
        try:
            return await fut
        finally:
            self._permission_waiters.pop(request_id, None)
            self._pending_permission_events.pop(request_id, None)

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

                # Trigger due schedules (best-effort). If there are no clients connected, scheduled runs
                # will still execute, but any permission prompts must be answered by a client.
                due = await self.runtime.schedules.pop_due()
                for s in due:
                    sched_id = str(s.get("id") or "")
                    title = str(s.get("title") or "") or sched_id
                    payload = s.get("payload") if isinstance(s.get("payload"), dict) else {}
                    user_input = str((payload or {}).get("text") or "")
                    run_id = f"run_sched_{uuid4().hex[:10]}"

                    async def _sched_runner(run_id: str, user_input: str, title: str, sched_id: str):
                        await self._broadcast_event(create_event(EventType.RUN_LOG, {"runId": "supervisor", "message": f"schedule triggered: {title} ({sched_id}) -> {run_id}"}))
                        try:
                            await self.runtime.schedules.set_last_run_id(schedule_id=sched_id, run_id=run_id)
                        except Exception:
                            pass
                        scheduled_input = f"[scheduled:{sched_id}] {user_input}".strip()
                        await self.start_run(
                            run_id=run_id,
                            user_input=scheduled_input,
                            send_event=self._broadcast_event,
                            ask_permission=lambda **kwargs: self._ask_permission_broadcast(**kwargs),
                        )

                    asyncio.create_task(_sched_runner(run_id, user_input, title, sched_id))
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

        try:
            await self._send_event(websocket, create_event(EventType.RUN_STATUS, {"runId": run_id, "status": "waiting_permission"}))
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
        except Exception:
            # If we can't prompt, treat as denied and abort the run.
            if not fut.done():
                fut.set_result("deny")
            raise
        try:
            return await fut
        finally:
            self._permission_waiters.pop(request_id, None)

    async def start_run(
        self,
        *,
        run_id: str,
        user_input: str,
        send_event: Callable[[dict], Awaitable[None]],
        ask_permission: Callable[..., Awaitable[str]],
    ) -> asyncio.Task:
        async def _runner() -> None:
            try:
                await send_event(create_event(EventType.RUN_STATUS, {"runId": run_id, "status": "running"}))
            except Exception:
                return
            try:
                async for ev in self.runtime.run(
                    run_id=run_id,
                    user_input=user_input,
                    policy=self.policy,
                    ask_permission=ask_permission,
                ):
                    try:
                        await send_event(ev)
                    except Exception:
                        return
            except Exception as e:
                try:
                    await send_event(create_event(EventType.RUN_ERROR, {"runId": run_id, "message": str(e)}))
                except Exception:
                    return

        return asyncio.create_task(_runner())

    async def handle_telegram_run_create(
        self,
        *,
        user_input: str,
        send_event: Callable[[dict], Awaitable[None]],
        ask_permission: Callable[..., Awaitable[str]],
    ) -> str:
        run_id = f"run_{uuid4().hex[:12]}"
        await self.start_run(
            run_id=run_id,
            user_input=user_input,
            send_event=send_event,
            ask_permission=ask_permission,
        )
        return run_id

    async def _persist_permission_if_needed(self, *, decision: str, remember: bool, capability: Any) -> None:
        cfg = config.load_config_uncached()
        remember_enabled = bool(((cfg.get("permissions") or {}).get("remember")) if isinstance(cfg, dict) else False)
        if remember_enabled and remember and isinstance(capability, str) and capability:
            try:
                Policy.persist_decision(capability=capability, decision=decision)
                self.policy = Policy.load()
            except Exception:
                pass

    async def handle_permission_respond(self, websocket: WebSocket, req: dict):
        params = (req.get("params") or {})
        request_id = params.get("requestId", "")
        decision = params.get("decision", "deny")
        remember = bool(params.get("remember", False))
        capability = params.get("capability")
        fut = self._permission_waiters.get(request_id)
        if fut and not fut.done():
            fut.set_result(decision)
            self._pending_permission_events.pop(request_id, None)
            await self._persist_permission_if_needed(decision=decision, remember=remember, capability=capability)
            await websocket.send_json(create_response(req.get("id", "unknown"), ok=True, payload={"requestId": request_id}))
            return
        await websocket.send_json(create_response(req.get("id", "unknown"), ok=False, error="Unknown or expired permission request"))

    async def handle_run_create(self, websocket: WebSocket, req: dict):
        params = req.get("params") or {}
        run_id = params.get("runId") or f"run_{uuid4().hex[:12]}"
        user_input = params.get("input", "")

        await websocket.send_json(create_response(req.get("id", "unknown"), ok=True, payload={"runId": run_id, "status": "accepted"}))
        await self.start_run(
            run_id=run_id,
            user_input=user_input,
            send_event=self._ws_sender(websocket),
            ask_permission=lambda **kwargs: self.ask_permission(websocket, **kwargs),
        )


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
            # Deliver any queued permission requests (offline-safe scheduled runs).
            for item in list(gateway._pending_permission_events.values()):
                try:
                    rid = str((item or {}).get("runId", "") or "")
                    ev = (item or {}).get("event")
                    if rid:
                        await gateway._send_event(websocket, create_event(EventType.RUN_STATUS, {"runId": rid, "status": "waiting_permission"}))
                    if isinstance(ev, dict):
                        await gateway._send_event(websocket, ev)
                except Exception:
                    # best-effort
                    pass

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
