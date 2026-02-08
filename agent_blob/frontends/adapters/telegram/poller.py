from __future__ import annotations

import asyncio
import json
import logging
from pathlib import Path
from typing import Any, Dict, Optional

from agent_blob import config
from agent_blob.frontends.adapters.telegram.client import TelegramClient
from agent_blob.frontends.adapters.telegram.renderer import TelegramRenderer

logger = logging.getLogger("agent_blob.telegram")


class TelegramPoller:
    def __init__(self, *, gateway: Any):
        self.gateway = gateway
        self.client = TelegramClient()
        self.renderer = TelegramRenderer(client=self.client)
        self.offset_path = Path(config.data_dir()) / "telegram_offset.json"
        self.media_root = Path(config.telegram_media_download_dir())

    async def run(self) -> None:
        self.offset_path.parent.mkdir(parents=True, exist_ok=True)
        if config.telegram_media_enabled() and config.telegram_media_download():
            self.media_root.mkdir(parents=True, exist_ok=True)

        offset = self._load_offset()
        poll_sleep = max(0.25, float(config.telegram_poll_interval_s()))
        logger.info("telegram poller started")

        while True:
            try:
                updates = await self.client.get_updates(offset=offset, timeout_s=20)
                if not updates:
                    await asyncio.sleep(poll_sleep)
                    continue
                for upd in updates:
                    uid = int(upd.get("update_id", 0) or 0)
                    await self._handle_update(upd)
                    offset = uid + 1
                    self._save_offset(offset)
            except Exception as e:
                logger.error("telegram poller error: %s", e)
                await asyncio.sleep(2.0)

    async def _handle_update(self, upd: Dict[str, Any]) -> None:
        cb = upd.get("callback_query")
        if isinstance(cb, dict):
            data = str(cb.get("data", "") or "")
            callback_id = str(cb.get("id", "") or "")
            handled = await self.renderer.handle_permission_callback(callback_query_id=callback_id, data=data)
            if not handled and callback_id:
                await self.client.answer_callback_query(callback_query_id=callback_id, text="unsupported")
            return

        msg = upd.get("message")
        if not isinstance(msg, dict):
            return
        chat = msg.get("chat")
        if not isinstance(chat, dict):
            return
        chat_id = int(chat.get("id", 0) or 0)
        if not chat_id:
            return

        text = str(msg.get("text", "") or "").strip()
        attachments = await self._extract_attachments(msg)

        if (not text) and (not attachments):
            return

        user_input = text
        if attachments:
            attachment_note = json.dumps({"attachments": attachments}, ensure_ascii=False)
            user_input = (f"{text}\n\n{attachment_note}" if text else attachment_note).strip()

        run_id = await self.gateway.handle_telegram_run_create(
            user_input=user_input,
            send_event=lambda ev: self.renderer.handle_event(ev, chat_id=chat_id),
            ask_permission=self.renderer.ask_permission,
        )
        logger.info("telegram run accepted: %s", run_id)

    async def _extract_attachments(self, msg: Dict[str, Any]) -> list[dict]:
        if not config.telegram_media_enabled():
            return []
        out: list[dict] = []

        # Photo (Telegram sends multiple sizes; pick the largest).
        photos = msg.get("photo")
        if isinstance(photos, list) and photos:
            best = photos[-1] if isinstance(photos[-1], dict) else None
            if isinstance(best, dict):
                rec = await self._materialize_file(
                    file_id=str(best.get("file_id", "") or ""),
                    file_size=int(best.get("file_size", 0) or 0),
                    kind="photo",
                    mime_type="image/jpeg",
                )
                if rec:
                    out.append(rec)

        # Document
        doc = msg.get("document")
        if isinstance(doc, dict):
            rec = await self._materialize_file(
                file_id=str(doc.get("file_id", "") or ""),
                file_size=int(doc.get("file_size", 0) or 0),
                kind="document",
                mime_type=str(doc.get("mime_type", "") or ""),
                filename=str(doc.get("file_name", "") or ""),
            )
            if rec:
                out.append(rec)

        # Voice
        voice = msg.get("voice")
        if isinstance(voice, dict):
            rec = await self._materialize_file(
                file_id=str(voice.get("file_id", "") or ""),
                file_size=int(voice.get("file_size", 0) or 0),
                kind="voice",
                mime_type=str(voice.get("mime_type", "") or "audio/ogg"),
            )
            if rec:
                out.append(rec)

        return out

    async def _materialize_file(
        self,
        *,
        file_id: str,
        file_size: int,
        kind: str,
        mime_type: str,
        filename: str = "",
    ) -> Optional[dict]:
        if not file_id:
            return None

        max_bytes = max(1, int(config.telegram_media_max_file_mb())) * 1024 * 1024
        if file_size > 0 and file_size > max_bytes:
            return {
                "kind": kind,
                "file_id": file_id,
                "mime_type": mime_type,
                "size": file_size,
                "skipped": True,
                "reason": "file_too_large",
            }

        rec: dict = {
            "kind": kind,
            "file_id": file_id,
            "mime_type": mime_type,
            "size": file_size,
            "filename": filename,
        }

        if not config.telegram_media_download():
            return rec

        try:
            info = await self.client.get_file(file_id=file_id)
            if not isinstance(info, dict) or not info.get("ok"):
                return rec
            result = info.get("result")
            if not isinstance(result, dict):
                return rec
            file_path = str(result.get("file_path", "") or "")
            if not file_path:
                return rec
            blob = await self.client.download_file_bytes(file_path=file_path)
            ext = Path(file_path).suffix or ""
            safe_name = f"{file_id}{ext}"
            local = self.media_root / safe_name
            local.write_bytes(blob)
            rec["local_path"] = str(local.resolve())
            return rec
        except Exception:
            return rec

    def _load_offset(self) -> Optional[int]:
        if not self.offset_path.exists():
            return None
        try:
            obj = json.loads(self.offset_path.read_text(encoding="utf-8"))
            if isinstance(obj, dict) and isinstance(obj.get("offset"), int):
                return int(obj["offset"])
        except Exception:
            return None
        return None

    def _save_offset(self, offset: int) -> None:
        self.offset_path.write_text(json.dumps({"offset": int(offset)}, ensure_ascii=False), encoding="utf-8")
