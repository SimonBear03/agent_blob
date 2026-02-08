from __future__ import annotations

import os
from typing import Any, Dict, List, Optional

import httpx


class TelegramClient:
    def __init__(self, *, token: Optional[str] = None, timeout_s: float = 30.0):
        self.token = str(token or os.getenv("TELEGRAM_BOT_TOKEN", "")).strip()
        if not self.token:
            raise RuntimeError("TELEGRAM_BOT_TOKEN is not set")
        self.base_url = f"https://api.telegram.org/bot{self.token}"
        self.file_base_url = f"https://api.telegram.org/file/bot{self.token}"
        self._client = httpx.AsyncClient(timeout=timeout_s)

    async def close(self) -> None:
        await self._client.aclose()

    async def get_updates(self, *, offset: Optional[int], timeout_s: int = 20) -> List[Dict[str, Any]]:
        payload: Dict[str, Any] = {"timeout": int(timeout_s), "allowed_updates": ["message", "callback_query"]}
        if offset is not None:
            payload["offset"] = int(offset)
        r = await self._client.post(f"{self.base_url}/getUpdates", json=payload)
        data = r.json()
        if not isinstance(data, dict) or not data.get("ok"):
            return []
        result = data.get("result")
        return result if isinstance(result, list) else []

    async def send_message(
        self,
        *,
        chat_id: int,
        text: str,
        reply_markup: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        payload: Dict[str, Any] = {"chat_id": int(chat_id), "text": str(text)}
        if reply_markup is not None:
            payload["reply_markup"] = reply_markup
        r = await self._client.post(f"{self.base_url}/sendMessage", json=payload)
        return r.json()

    async def edit_message_text(
        self,
        *,
        chat_id: int,
        message_id: int,
        text: str,
        reply_markup: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        payload: Dict[str, Any] = {"chat_id": int(chat_id), "message_id": int(message_id), "text": str(text)}
        if reply_markup is not None:
            payload["reply_markup"] = reply_markup
        r = await self._client.post(f"{self.base_url}/editMessageText", json=payload)
        return r.json()

    async def answer_callback_query(self, *, callback_query_id: str, text: str = "") -> Dict[str, Any]:
        payload: Dict[str, Any] = {"callback_query_id": str(callback_query_id)}
        if text:
            payload["text"] = str(text)
        r = await self._client.post(f"{self.base_url}/answerCallbackQuery", json=payload)
        return r.json()

    async def get_file(self, *, file_id: str) -> Dict[str, Any]:
        r = await self._client.post(f"{self.base_url}/getFile", json={"file_id": str(file_id)})
        return r.json()

    async def download_file_bytes(self, *, file_path: str) -> bytes:
        r = await self._client.get(f"{self.file_base_url}/{file_path.lstrip('/')}")
        return bytes(r.content)

