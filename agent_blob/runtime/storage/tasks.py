from __future__ import annotations

import json
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Optional, Tuple

from .paths import data_dir
from .jsonl_archive import rotate_jsonl, prune_archives
from agent_blob import config


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

    async def ensure_task(self, *, task_id: str, title: str) -> str:
        """
        Ensure a task with a specific id exists (used for stable, system-owned contexts like schedules).
        Returns task_id.
        """
        tid = str(task_id or "").strip()
        if not tid:
            raise ValueError("Missing task_id")
        data = self._load()
        now = time.time()
        if tid not in data or not isinstance(data.get(tid), dict):
            data[tid] = {
                "id": tid,
                "status": "open",
                "title": (title or "").strip()[:120],
                "created_at": now,
                "updated_at": now,
                "run_ids": [],
            }
            self._append_event({"type": "task.created", "taskId": tid, "runId": None, "system": True})
        else:
            # Update title if it's empty and we have a better one.
            t = data[tid]
            if isinstance(t, dict):
                if not str(t.get("title") or "").strip() and (title or "").strip():
                    t["title"] = (title or "").strip()[:120]
                    t["updated_at"] = now
                    data[tid] = t
        self._save(data)
        return tid

    async def create_task(self, *, run_id: str, title: str) -> str:
        data = self._load()
        task_id = f"task_{int(time.time()*1000)}"
        now = time.time()
        data[task_id] = {
            "id": task_id,
            "status": "open",
            "title": (title or "").strip()[:120],
            "created_at": now,
            "updated_at": now,
            "run_ids": [run_id],
        }
        self._save(data)
        self._append_event({"type": "task.created", "taskId": task_id, "runId": run_id})
        return task_id

    async def attach_run(self, *, task_id: str, run_id: str) -> bool:
        data = self._load()
        task = data.get(task_id)
        if not isinstance(task, dict):
            return False
        run_ids = list(task.get("run_ids") or [])
        if run_id not in run_ids:
            run_ids.append(run_id)
        task["run_ids"] = run_ids
        task["updated_at"] = time.time()
        self._save(data)
        self._append_event({"type": "task.attached", "taskId": task_id, "runId": run_id})
        return True

    async def set_status(self, *, task_id: str, status: str) -> None:
        data = self._load()
        task = data.get(task_id)
        if not task:
            return
        task["status"] = status
        task["updated_at"] = time.time()
        self._save(data)
        self._append_event({"type": "task.status", "taskId": task_id, "status": status})

    async def most_recent_active(self) -> Optional[dict]:
        tasks = await self.list_tasks()
        for t in tasks:
            status = str(t.get("status", "") or "")
            if status not in ("done", "cancelled", "failed"):
                return t
        return None

    async def most_recent_within(self, *, window_s: int, include_terminal: bool = False) -> Optional[dict]:
        """
        Return the most recently updated task within the given time window.

        If include_terminal is False, terminal tasks (done/cancelled/failed) are ignored.
        """
        window_s = max(0, int(window_s))
        if window_s <= 0:
            return None
        now = time.time()
        tasks = await self.list_tasks()
        for t in tasks:
            status = str(t.get("status", "") or "")
            if (not include_terminal) and status in ("done", "cancelled", "failed"):
                continue
            updated = float(t.get("updated_at", 0) or 0)
            if now - updated <= window_s:
                return t
        return None

    async def auto_close_inactive(self, *, older_than_s: int) -> Dict[str, int]:
        """
        Convert stale non-terminal tasks to done if they haven't been updated recently.

        This prevents tasks.json from growing unbounded with perpetual "open" tasks.
        Returns {closed:int, total:int}.
        """
        older_than_s = max(0, int(older_than_s))
        if older_than_s <= 0:
            return {"closed": 0, "total": 0}

        data = self._load()
        now = time.time()
        terminal_statuses = {"done", "cancelled", "failed"}
        closed = 0

        for tid, t in list(data.items()):
            if not isinstance(t, dict):
                continue
            status = str(t.get("status", "") or "")
            if status in terminal_statuses:
                continue
            updated = float(t.get("updated_at", 0) or 0)
            if (now - updated) >= older_than_s:
                t["status"] = "done"
                t["updated_at"] = now
                data[tid] = t
                closed += 1
                self._append_event({"type": "task.autoclosed", "taskId": tid})

        if closed:
            self._save(data)
        return {"closed": closed, "total": len(data)}

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

    async def rotate_and_prune_events(self) -> Dict[str, Any]:
        d = self._tasks.parent
        rec = rotate_jsonl(
            data_dir=d,
            kind="tasks_events",
            active_path=self._events,
            max_bytes=config.log_max_bytes("tasks_events", 5_000_000),
        )
        pruned = prune_archives(
            data_dir=d,
            kind="tasks_events",
            keep_days=config.log_keep_days("tasks_events", 30),
            keep_max_files=config.log_keep_max_files("tasks_events", 50),
        )
        return {"rotated": bool(rec), "pruned": pruned}

    def _append_event(self, ev: dict) -> None:
        with self._events.open("a", encoding="utf-8") as f:
            f.write(json.dumps(ev, ensure_ascii=False) + "\n")
