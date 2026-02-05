from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Optional


class EventType:
    RUN_STATUS = "run.status"
    RUN_LOG = "run.log"
    RUN_TOKEN = "run.token"
    RUN_FINAL = "run.final"
    RUN_ERROR = "run.error"
    PERMISSION_REQUEST = "permission.request"


def create_response(
    request_id: str,
    *,
    ok: bool,
    payload: Optional[Dict[str, Any]] = None,
    error: Optional[str] = None,
) -> dict:
    return {"type": "res", "id": request_id, "ok": ok, "payload": payload, "error": error}


def create_event(event: str, payload: Dict[str, Any], seq: Optional[int] = None) -> dict:
    return {"type": "event", "event": event, "payload": payload, "seq": seq}

