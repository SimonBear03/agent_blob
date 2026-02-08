from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass
from typing import Any, Dict, Optional

from agent_blob import config
from agent_blob.frontends.adapters.telegram.client import TelegramClient


@dataclass
class RunView:
    chat_id: int
    stream_message_id: Optional[int] = None
    stream_buffer: str = ""
    last_flush_ms: int = 0
    done: bool = False


class TelegramRenderer:
    def __init__(self, *, client: TelegramClient):
        self.client = client
        self._runs: Dict[str, RunView] = {}
        self._permission_waiters: Dict[str, asyncio.Future[str]] = {}

    async def ask_permission(
        self,
        *,
        run_id: str,
        capability: str,
        preview: str,
        reason: str,
    ) -> str:
        view = self._runs.get(run_id)
        if not view:
            return "deny"
        req_id = f"tg_perm_{int(time.time() * 1000)}_{len(self._permission_waiters)}"
        fut: asyncio.Future[str] = asyncio.get_running_loop().create_future()
        self._permission_waiters[req_id] = fut

        text = (
            f"[{run_id}] permission required: {capability}\n"
            f"reason: {reason}\n"
            f"preview:\n{preview[:1000]}"
        )
        markup = {
            "inline_keyboard": [
                [
                    {"text": "Allow", "callback_data": f"perm:allow:{req_id}"},
                    {"text": "Deny", "callback_data": f"perm:deny:{req_id}"},
                ]
            ]
        }
        await self.client.send_message(chat_id=view.chat_id, text=text, reply_markup=markup)
        try:
            return await fut
        finally:
            self._permission_waiters.pop(req_id, None)

    async def handle_permission_callback(self, *, callback_query_id: str, data: str) -> bool:
        if not data.startswith("perm:"):
            return False
        parts = data.split(":", 2)
        if len(parts) != 3:
            return False
        _, decision, req_id = parts
        decision = "allow" if decision == "allow" else "deny"
        fut = self._permission_waiters.get(req_id)
        if fut and not fut.done():
            fut.set_result(decision)
            await self.client.answer_callback_query(callback_query_id=callback_query_id, text=f"{decision}")
            return True
        await self.client.answer_callback_query(callback_query_id=callback_query_id, text="expired")
        return True

    async def handle_event(self, event: Dict[str, Any], *, chat_id: int) -> None:
        event_name = str(event.get("event", "") or "")
        payload = event.get("payload") if isinstance(event.get("payload"), dict) else {}
        run_id = str(payload.get("runId", "") or "")
        if not run_id:
            return
        view = self._runs.setdefault(run_id, RunView(chat_id=chat_id))
        if event_name == "run.status":
            await self._render_status(run_id=run_id, status=str(payload.get("status", "") or ""), view=view)
            return
        if event_name == "run.token":
            token = str(payload.get("content", "") or "")
            if token:
                view.stream_buffer += token
                await self._flush_stream(run_id=run_id, view=view, force=False)
            return
        if event_name == "run.log":
            msg = str(payload.get("message", "") or "").strip()
            if msg:
                await self.client.send_message(chat_id=chat_id, text=f"[{run_id}] {msg}")
            return
        if event_name == "run.tool_call":
            tool = str(payload.get("toolName", "") or "")
            await self.client.send_message(chat_id=chat_id, text=f"[{run_id}] tool_call: {tool}")
            return
        if event_name == "run.error":
            msg = str(payload.get("message", "") or "").strip() or "error"
            await self._flush_stream(run_id=run_id, view=view, force=True)
            await self.client.send_message(chat_id=chat_id, text=f"[{run_id}] ERROR: {msg}")
            view.done = True
            return
        if event_name == "run.final":
            await self._flush_stream(run_id=run_id, view=view, force=True)
            await self.client.send_message(chat_id=chat_id, text=f"[{run_id}] done")
            view.done = True
            return

    async def _render_status(self, *, run_id: str, status: str, view: RunView) -> None:
        verbosity = config.telegram_status_verbosity().strip().lower()
        if verbosity == "off":
            return
        if verbosity == "minimal" and status not in {"running", "waiting_permission", "done"}:
            return
        await self.client.send_message(chat_id=view.chat_id, text=f"[{run_id}] status: {status}")

    async def _flush_stream(self, *, run_id: str, view: RunView, force: bool) -> None:
        now_ms = int(time.time() * 1000)
        interval = max(50, int(config.telegram_stream_edit_interval_ms()))
        if (not force) and (now_ms - view.last_flush_ms < interval):
            return
        text = view.stream_buffer.strip()
        if not text:
            return
        max_chars = max(200, int(config.telegram_max_message_chars()))
        text = text[-max_chars:]
        if view.stream_message_id is None:
            res = await self.client.send_message(chat_id=view.chat_id, text=f"[{run_id}] {text}")
            if isinstance(res, dict) and res.get("ok") and isinstance(res.get("result"), dict):
                msg = res["result"]
                mid = msg.get("message_id")
                if isinstance(mid, int):
                    view.stream_message_id = mid
        else:
            await self.client.edit_message_text(
                chat_id=view.chat_id,
                message_id=view.stream_message_id,
                text=f"[{run_id}] {text}",
            )
        view.last_flush_ms = now_ms
