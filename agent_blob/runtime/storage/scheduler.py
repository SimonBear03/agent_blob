from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any, Dict, Optional

from datetime import datetime, timedelta
import re
from zoneinfo import ZoneInfo

from .paths import data_dir
from agent_blob import config


class SchedulerStore:
    """
    Minimal schedule persistence.

    v2 MVP:
    - schedules.json holds current schedules
    - schedules are interval-based (every N seconds)
    - supervisor ticks and triggers due schedules via the same run pipeline
    """

    def __init__(self):
        self._path = data_dir() / "schedules.json"

    async def startup(self) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        if not self._path.exists():
            self._path.write_text("[]", encoding="utf-8")
        # One-time migrate on startup so existing schedules get normalized.
        items = self._load()
        migrated, changed = self._migrate(items)
        if changed:
            self._save(migrated)

    def _load(self) -> list[dict]:
        try:
            return json.loads(self._path.read_text(encoding="utf-8"))
        except Exception:
            return []

    def _save(self, items: list[dict]) -> None:
        tmp = self._path.with_suffix(".tmp")
        tmp.write_text(json.dumps(items, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        tmp.replace(self._path)

    async def list_schedules(self) -> list[dict]:
        items, _ = self._migrate(self._load())
        items.sort(key=lambda x: float(x.get("next_run_at", 0)), reverse=False)
        return items

    def _migrate(self, items: list[dict]) -> tuple[list[dict], bool]:
        """
        Normalize schedules to an OpenClaw-like typed shape:
          {id, type, title, enabled, schedule:{...}, payload:{kind,text}, next_run_at, ...}
        """
        changed = False
        out: list[dict] = []
        for s in items:
            if not isinstance(s, dict):
                changed = True
                continue
            if "payload" in s and isinstance(s.get("payload"), dict) and "schedule" in s and isinstance(s.get("schedule"), dict):
                out.append(s)
                continue

            # Legacy format migration.
            stype = str(s.get("type", "") or "")
            sid = str(s.get("id", "") or "").strip() or f"sched_{int(time.time()*1000)}"
            prompt = str(s.get("input", "") or "")
            prompt = self._sanitize_input(prompt)
            title = str(s.get("title", "") or "").strip()[:120] or (prompt.strip()[:120] if prompt else sid)
            enabled = bool(s.get("enabled", True))
            tz = s.get("tz")

            schedule: dict = {}
            if stype == "interval":
                schedule = {"interval_s": int(s.get("interval_s", 60) or 60)}
            elif stype == "cron":
                schedule = {"cron": str(s.get("cron", "") or "").strip()}
            else:
                schedule = {}

            rec = {
                "id": sid,
                "type": stype or "interval",
                "title": title,
                "enabled": enabled,
                "schedule": schedule,
                "payload": {"kind": "prompt", "text": prompt},
                "tz": str(tz).strip() if tz else None,
                "created_at": float(s.get("created_at", time.time()) or time.time()),
                "updated_at": float(s.get("updated_at", time.time()) or time.time()),
                "next_run_at": float(s.get("next_run_at", 0) or 0),
                "last_run_at": s.get("last_run_at"),
                "last_run_id": s.get("last_run_id"),
            }
            out.append(rec)
            changed = True
        return out, changed

    async def create_interval(
        self,
        *,
        input: str,
        interval_s: int,
        enabled: bool = True,
        title: Optional[str] = None,
    ) -> dict:
        items, _ = self._migrate(self._load())
        now = time.time()
        interval_s = max(1, int(interval_s))
        sched_id = f"sched_{int(now*1000)}"
        input_text = self._sanitize_input(str(input or ""))
        rec = {
            "id": sched_id,
            "type": "interval",
            "title": (title or input_text or "").strip()[:120],
            "enabled": bool(enabled),
            "created_at": now,
            "updated_at": now,
            "next_run_at": now + interval_s,
            "last_run_at": None,
            "last_run_id": None,
            "schedule": {"interval_s": interval_s},
            "payload": {"kind": "prompt", "text": input_text},
            "tz": None,
        }
        items.append(rec)
        self._save(items)
        return rec

    def _sanitize_input(self, text: str) -> str:
        """
        Schedules should store user-like instructions, not pseudo tool calls.
        The LLM sometimes passes strings like shell_run({...}) which won't execute.
        Rewrite a small set of common tool-like patterns into natural language.
        """
        s = (text or "").strip()
        if not s:
            return ""

        low = s.lower()

        # shell_run('echo hi')
        m = re.search(r"shell_run\s*\(\s*['\"]([^'\"]+)['\"]\s*\)\s*$", s, flags=re.IGNORECASE)
        if m:
            cmd = m.group(1).strip()
            return f"Run `{cmd}` in the shell."

        # shell_run({'command': 'echo hi'}) or shell_run({"command":"echo hi"})
        if "shell_run" in low and "command" in low:
            m2 = re.search(r"command['\"]?\s*:\s*['\"]([^'\"]+)['\"]", s, flags=re.IGNORECASE)
            if m2:
                cmd = m2.group(1).strip()
                return f"Run `{cmd}` in the shell."

        return s

    def _tzinfo(self, tz_name: Optional[str]):
        if tz_name:
            return ZoneInfo(tz_name)
        cfg_tz = config.scheduler_timezone()
        if cfg_tz:
            return ZoneInfo(cfg_tz)
        # Fall back to system local tz offset.
        return datetime.now().astimezone().tzinfo

    def _parse_cron_field(self, field: str, *, min_v: int, max_v: int) -> set[int] | None:
        """
        Very small cron field parser: '*' or comma-separated ints.
        Returns None for '*' meaning "any".
        """
        s = str(field or "").strip()
        if not s or s == "*":
            return None
        vals: set[int] = set()
        for part in s.split(","):
            part = part.strip()
            if not part:
                continue
            if not part.isdigit():
                raise ValueError(f"Unsupported cron field: {field}")
            v = int(part)
            if v < min_v or v > max_v:
                raise ValueError(f"Cron value out of range: {v} ({min_v}-{max_v})")
            vals.add(v)
        return vals or None

    def _parse_cron(self, expr: str) -> dict:
        """
        Parse 5-field cron: 'min hour dom mon dow'
        Supported: '*' or comma-separated integers per field.
        """
        parts = [p for p in str(expr or "").strip().split() if p]
        if len(parts) != 5:
            raise ValueError("Cron expression must have 5 fields: min hour dom mon dow")
        minute, hour, dom, mon, dow = parts
        return {
            "minute": self._parse_cron_field(minute, min_v=0, max_v=59),
            "hour": self._parse_cron_field(hour, min_v=0, max_v=23),
            "dom": self._parse_cron_field(dom, min_v=1, max_v=31),
            "mon": self._parse_cron_field(mon, min_v=1, max_v=12),
            # 0=Sunday ... 6=Saturday
            "dow": self._parse_cron_field(dow, min_v=0, max_v=6),
        }

    def _cron_matches(self, dt: datetime, spec: dict) -> bool:
        if spec.get("minute") is not None and dt.minute not in spec["minute"]:
            return False
        if spec.get("hour") is not None and dt.hour not in spec["hour"]:
            return False
        if spec.get("dom") is not None and dt.day not in spec["dom"]:
            return False
        if spec.get("mon") is not None and dt.month not in spec["mon"]:
            return False
        if spec.get("dow") is not None:
            # Python: Monday=0..Sunday=6. Cron: Sunday=0..Saturday=6.
            cron_dow = (dt.weekday() + 1) % 7
            if cron_dow not in spec["dow"]:
                return False
        return True

    def _next_cron_run_at(self, *, expr: str, tz_name: Optional[str], now: float) -> float:
        tz = self._tzinfo(tz_name)
        spec = self._parse_cron(expr)
        base = datetime.fromtimestamp(now, tz=tz)
        # Start searching at the next minute boundary.
        cur = base.replace(second=0, microsecond=0) + timedelta(minutes=1)
        # Bound search to avoid infinite loops with unsupported expressions.
        limit = cur + timedelta(days=370)
        while cur <= limit:
            if self._cron_matches(cur, spec):
                return cur.timestamp()
            cur = cur + timedelta(minutes=1)
        raise ValueError("Cron next-run search exceeded limit (expression too restrictive?)")

    async def create_cron(
        self,
        *,
        input: str,
        cron: str,
        tz: Optional[str] = None,
        enabled: bool = True,
        title: Optional[str] = None,
    ) -> dict:
        items, _ = self._migrate(self._load())
        now = time.time()
        sched_id = f"sched_{int(now*1000)}"
        next_run_at = self._next_cron_run_at(expr=cron, tz_name=tz, now=now)
        input_text = self._sanitize_input(str(input or ""))
        rec = {
            "id": sched_id,
            "type": "cron",
            "title": (title or input_text or "").strip()[:120],
            "enabled": bool(enabled),
            "created_at": now,
            "updated_at": now,
            "next_run_at": next_run_at,
            "last_run_at": None,
            "last_run_id": None,
            "schedule": {"cron": str(cron or "").strip()},
            "payload": {"kind": "prompt", "text": input_text},
            "tz": str(tz).strip() if tz else None,
        }
        items.append(rec)
        self._save(items)
        return rec

    async def create_daily(
        self,
        *,
        input: str,
        hour: int,
        minute: int,
        tz: Optional[str] = None,
        enabled: bool = True,
        title: Optional[str] = None,
    ) -> dict:
        hour = int(hour)
        minute = int(minute)
        if hour < 0 or hour > 23 or minute < 0 or minute > 59:
            raise ValueError("hour must be 0-23 and minute must be 0-59")
        cron = f"{minute} {hour} * * *"
        return await self.create_cron(input=input, cron=cron, tz=tz, enabled=enabled, title=title)

    async def delete(self, *, schedule_id: str) -> dict:
        sid = str(schedule_id or "").strip()
        items, _ = self._migrate(self._load())
        before = len(items)
        items = [s for s in items if str(s.get("id", "")) != sid]
        removed = before - len(items)
        if removed:
            self._save(items)
        return {"ok": bool(removed), "removed": removed, "id": sid}

    async def set_enabled(self, *, schedule_id: str, enabled: bool) -> dict:
        sid = str(schedule_id or "").strip()
        if not sid:
            return {"ok": False, "error": "Missing schedule id"}
        items, _ = self._migrate(self._load())
        changed = False
        for s in items:
            if not isinstance(s, dict):
                continue
            if str(s.get("id", "")) != sid:
                continue
            s["enabled"] = bool(enabled)
            s["updated_at"] = time.time()
            changed = True
            break
        if changed:
            self._save(items)
            return {"ok": True, "id": sid, "enabled": bool(enabled)}
        return {"ok": False, "error": "Schedule not found", "id": sid}

    async def pop_due(self, *, now: Optional[float] = None) -> list[dict]:
        """
        Return schedules due to run, and advance their next_run_at.
        """
        items, _ = self._migrate(self._load())
        t = float(now if now is not None else time.time())
        due: list[dict] = []
        changed = False
        for s in items:
            if not isinstance(s, dict):
                continue
            if not bool(s.get("enabled", True)):
                continue
            next_run = float(s.get("next_run_at", 0) or 0)
            if next_run <= t:
                due.append(dict(s))
                s["last_run_at"] = t
                stype = str(s.get("type", "") or "")
                sched = s.get("schedule") if isinstance(s.get("schedule"), dict) else {}
                if stype == "interval":
                    interval_s = max(1, int((sched or {}).get("interval_s", 60) or 60))
                    s["next_run_at"] = t + interval_s
                elif stype == "cron":
                    expr = str((sched or {}).get("cron", "") or "")
                    tz_name = s.get("tz")
                    s["next_run_at"] = self._next_cron_run_at(expr=expr, tz_name=str(tz_name) if tz_name else None, now=t)
                else:
                    # Unknown type; disable it so it doesn't spin.
                    s["enabled"] = False
                    s["next_run_at"] = t + 365 * 86400
                s["updated_at"] = t
                changed = True
        if changed:
            self._save(items)
        due.sort(key=lambda x: float(x.get("next_run_at", 0)), reverse=False)
        return due

    async def set_last_run_id(self, *, schedule_id: str, run_id: str) -> bool:
        sid = str(schedule_id or "").strip()
        rid = str(run_id or "").strip()
        if not sid or not rid:
            return False
        items, _ = self._migrate(self._load())
        changed = False
        for s in items:
            if not isinstance(s, dict):
                continue
            if str(s.get("id", "")) != sid:
                continue
            s["last_run_id"] = rid
            s["updated_at"] = time.time()
            changed = True
            break
        if changed:
            self._save(items)
        return changed
