from __future__ import annotations

import json
import time
from pathlib import Path

from .paths import data_dir


class SchedulerStore:
    """
    Minimal schedule persistence.

    v1 supports listing schedules. Execution/creation will come next.
    """

    def __init__(self):
        self._path = data_dir() / "schedules.json"

    async def startup(self) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        if not self._path.exists():
            self._path.write_text("[]", encoding="utf-8")

    def _load(self) -> list[dict]:
        try:
            return json.loads(self._path.read_text(encoding="utf-8"))
        except Exception:
            return []

    async def list_schedules(self) -> list[dict]:
        items = self._load()
        items.sort(key=lambda x: float(x.get("next_run_at", 0)), reverse=False)
        return items

