from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Tuple
from collections import deque

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

    async def recent_turns(self, limit: int = 8) -> List[Dict[str, Any]]:
        """
        Reconstruct recent user/assistant turns from run.input/run.output events.
        Best-effort and bounded: scans only the last ~2000 events.
        """
        if not self._path.exists():
            return []

        last_lines: deque[str] = deque(maxlen=2000)
        with self._path.open("r", encoding="utf-8") as f:
            for line in f:
                last_lines.append(line)

        by_run: Dict[str, Dict[str, Any]] = {}
        ordered: List[str] = []
        for raw in last_lines:
            raw = raw.strip()
            if not raw:
                continue
            try:
                ev = json.loads(raw)
            except Exception:
                continue
            r = ev.get("runId")
            t = ev.get("type")
            if not isinstance(r, str) or not isinstance(t, str):
                continue
            if r not in by_run:
                by_run[r] = {"runId": r}
                ordered.append(r)
            if t == "run.input":
                by_run[r]["user"] = ev.get("input", "")
            elif t == "run.output":
                by_run[r]["assistant"] = ev.get("text", "")

        turns: List[Dict[str, Any]] = []
        for r in ordered:
            rec = by_run.get(r) or {}
            user = rec.get("user")
            assistant = rec.get("assistant")
            if isinstance(user, str) and isinstance(assistant, str) and user and assistant:
                turns.append({"runId": r, "user": user, "assistant": assistant})

        return turns[-limit:]

    async def search_turns(self, query: str, limit: int = 5) -> List[Dict[str, Any]]:
        """
        Best-effort keyword search over recent reconstructed turns.
        Scans the same bounded tail as recent_turns().
        """
        q = (query or "").lower().strip()
        if not q:
            return []
        turns = await self.recent_turns(limit=200)  # bounded by internal scan
        scored: List[Tuple[int, Dict[str, Any]]] = []
        for t in turns:
            u = str(t.get("user", "")).lower()
            a = str(t.get("assistant", "")).lower()
            if q in u or q in a:
                # crude score: longer match gets more
                scored.append((len(u) + len(a), t))
        scored.sort(key=lambda x: x[0], reverse=True)
        return [t for _, t in scored[:limit]]
