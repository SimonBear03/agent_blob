from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Tuple
from collections import deque

from .paths import data_dir
from .jsonl_archive import rotate_jsonl, prune_archives
from agent_blob import config


class EventLog:
    def __init__(self):
        self._data_dir = data_dir()
        self._path = self._data_dir / "events.jsonl"

    async def startup(self) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        if not self._path.exists():
            self._path.write_text("", encoding="utf-8")

    async def append(self, event: Dict[str, Any]) -> None:
        line = json.dumps(event, ensure_ascii=False)
        with self._path.open("a", encoding="utf-8") as f:
            f.write(line + "\n")

    async def rotate_and_prune(self) -> Dict[str, Any]:
        rec = rotate_jsonl(
            data_dir=self._data_dir,
            kind="events",
            active_path=self._path,
            max_bytes=config.log_max_bytes("events", 20_000_000),
        )
        pruned = prune_archives(
            data_dir=self._data_dir,
            kind="events",
            keep_days=config.log_keep_days("events", 14),
            keep_max_files=config.log_keep_max_files("events", 50),
        )
        return {"rotated": bool(rec), "pruned": pruned}

    async def recent_turns(self, limit: int = 8) -> List[Dict[str, Any]]:
        """
        Reconstruct recent user/assistant turns from run.input/run.output events.
        Best-effort and bounded: scans only the last ~2000 events across the active log and recent archives.
        """
        if not self._path.exists():
            return []

        last_lines: deque[str] = deque(maxlen=2000)
        for line in self._iter_tail_lines(max_lines=2000):
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
                if "taskId" in ev:
                    by_run[r]["taskId"] = ev.get("taskId")
            elif t == "run.output":
                by_run[r]["assistant"] = ev.get("text", "")
                if "taskId" in ev:
                    by_run[r]["taskId"] = ev.get("taskId")

        turns: List[Dict[str, Any]] = []
        for r in ordered:
            rec = by_run.get(r) or {}
            user = rec.get("user")
            assistant = rec.get("assistant")
            if isinstance(user, str) and isinstance(assistant, str) and user and assistant:
                t = {"runId": r, "user": user, "assistant": assistant}
                if rec.get("taskId"):
                    t["taskId"] = rec.get("taskId")
                turns.append(t)

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
        q_terms = [t for t in q.replace(".", " ").replace(",", " ").split() if t]
        scored: List[Tuple[float, Dict[str, Any]]] = []
        n = max(1, len(turns))
        for i, t in enumerate(turns):
            u = str(t.get("user", "")).lower()
            a = str(t.get("assistant", "")).lower()
            hay = f"{u}\n{a}"
            if q not in hay and not any(term in hay for term in q_terms):
                continue
            overlap = sum(1 for term in q_terms if term in hay)
            recency = float(i) / float(n)  # newer turns have higher i
            scored.append((overlap * 3.0 + recency, t))
        scored.sort(key=lambda x: x[0], reverse=True)
        return [t for _, t in scored[:limit]]

    def _iter_tail_lines(self, *, max_lines: int) -> List[str]:
        """
        Read a bounded tail of lines across the active log and most recent archives.
        """
        max_lines = max(0, int(max_lines))
        if max_lines <= 0:
            return []

        files: List[Path] = []
        arch = (self._data_dir / "archives")
        if arch.exists():
            candidates = sorted(arch.glob("events_*.jsonl"), key=lambda p: p.stat().st_mtime, reverse=True)
            recent = candidates[:5]  # cap: search up to 5 recent archives
            files.extend(list(reversed(recent)))  # chronological: oldest -> newest
        files.append(self._path)

        out: deque[str] = deque()
        remaining = max_lines
        for p in files:
            lines = _tail_lines(p, remaining)
            for line in lines:
                out.append(line)
            remaining = max_lines - len(out)
            if remaining <= 0:
                break
        return list(out)[-max_lines:]


def _tail_lines(path: Path, max_lines: int, block_size: int = 64 * 1024) -> List[str]:
    """
    Efficiently read the last max_lines lines of a text file.
    """
    max_lines = max(0, int(max_lines))
    if max_lines <= 0 or not path.exists():
        return []

    data = b""
    try:
        with path.open("rb") as f:
            f.seek(0, 2)
            end = f.tell()
            pos = end
            while pos > 0 and data.count(b"\n") <= max_lines:
                read_size = min(block_size, pos)
                pos -= read_size
                f.seek(pos)
                data = f.read(read_size) + data
                if pos == 0:
                    break
    except Exception:
        return []

    try:
        text = data.decode("utf-8", errors="replace")
    except Exception:
        return []
    lines = text.splitlines()
    return lines[-max_lines:]
