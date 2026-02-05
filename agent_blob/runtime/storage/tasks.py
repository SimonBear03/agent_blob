from __future__ import annotations

import json
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Optional

from .paths import data_dir


class TaskStore:
    """
    Durable task ledger.
    MVP: tasks.json is the current state; tasks_events.jsonl is append-only history.
    """

    def __init__(self):
        d = data_dir()
        self._tasks = d / "tasks.json"
        self._events = d / "tasks_events.jsonl"

    async def startup(self) -> None:
        self._tasks.parent.mkdir(parents=True, exist_ok=True)
        if not self._tasks.exists():
            self._tasks.write_text("{}", encoding="utf-8")
        if not self._events.exists():
            self._events.write_text("", encoding="utf-8")

    def _load(self) -> dict:
        try:
            return json.loads(self._tasks.read_text(encoding="utf-8"))
        except Exception:
            return {}

    def _save(self, data: dict) -> None:
        self._tasks.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")

    async def upsert_from_input(self, *, run_id: str, user_input: str) -> str:
        data = self._load()
        task_id = f"task_{int(time.time()*1000)}"
        now = time.time()
        data[task_id] = {
            "id": task_id,
            "status": "running",
            "title": (user_input or "").strip()[:80],
            "created_at": now,
            "updated_at": now,
            "run_ids": [run_id],
        }
        self._save(data)
        self._append_event({"type": "task.created", "taskId": task_id, "runId": run_id})
        return task_id

    async def mark_done(self, *, task_id: str) -> None:
        data = self._load()
        task = data.get(task_id)
        if not task:
            return
        task["status"] = "done"
        task["updated_at"] = time.time()
        self._save(data)
        self._append_event({"type": "task.done", "taskId": task_id})

    async def list_tasks(self) -> list[dict]:
        data = self._load()
        tasks = list(data.values())
        tasks.sort(key=lambda t: float(t.get("updated_at", 0)), reverse=True)
        return tasks

    async def purge_done(self, *, keep_days: int = 30, keep_max: int = 200) -> dict:
        """
        Purge completed/cancelled/failed tasks from tasks.json, keeping:
        - all non-terminal tasks
        - terminal tasks updated within keep_days
        - at most keep_max terminal tasks (most recent)

        Returns {removed:int, kept:int}.
        """
        data = self._load()
        now = time.time()
        cutoff = now - (keep_days * 86400)

        terminal_statuses = {"done", "cancelled", "failed"}
        terminal = []
        active = {}

        for tid, t in list(data.items()):
            status = str(t.get("status", "") or "")
            updated = float(t.get("updated_at", 0) or 0)
            if status in terminal_statuses:
                terminal.append((updated, tid, t))
            else:
                active[tid] = t

        # Keep terminal tasks within retention window
        terminal_kept = [(u, tid, t) for (u, tid, t) in terminal if u >= cutoff]
        terminal_kept.sort(key=lambda x: x[0], reverse=True)
        terminal_kept = terminal_kept[: max(0, int(keep_max))]

        new_data = dict(active)
        for _, tid, t in terminal_kept:
            new_data[tid] = t

        removed = len(data) - len(new_data)
        if removed > 0:
            self._save(new_data)
            self._append_event({"type": "tasks.purged", "removed": removed, "kept": len(new_data)})

        return {"removed": removed, "kept": len(new_data)}

    def _append_event(self, ev: dict) -> None:
        with self._events.open("a", encoding="utf-8") as f:
            f.write(json.dumps(ev, ensure_ascii=False) + "\n")
