from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict

from .paths import data_dir


class EventLog:
    def __init__(self):
        self._path = data_dir() / "events.jsonl"

    async def startup(self) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        if not self._path.exists():
            self._path.write_text("", encoding="utf-8")

    async def append(self, event: Dict[str, Any]) -> None:
        line = json.dumps(event, ensure_ascii=False)
        with self._path.open("a", encoding="utf-8") as f:
            f.write(line + "\n")
