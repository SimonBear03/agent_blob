from __future__ import annotations

import json
import time
import hashlib
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from .paths import data_dir


class MemoryStore:
    """
    V2 skeleton memory:
    - pinned.json: small curated list (always loaded)
    - memories.jsonl: append-only extracted memory candidates
    - memory_state.json: consolidated, deduped memory state (keyed)

    All retrieval/indexing is intentionally minimal here; this is designed
    to be swapped with BM25 + embeddings later without changing the runtime API.
    """

    def __init__(self):
        d = data_dir()
        self._pinned = d / "pinned.json"
        self._structured = d / "memories.jsonl"
        self._state = d / "memory_state.json"
        self._state_meta = d / "memory_state.meta.json"

    async def startup(self) -> None:
        self._pinned.parent.mkdir(parents=True, exist_ok=True)
        if not self._pinned.exists():
            self._pinned.write_text("[]", encoding="utf-8")
        if not self._structured.exists():
            self._structured.write_text("", encoding="utf-8")
        if not self._state.exists():
            self._state.write_text("{}", encoding="utf-8")
        if not self._state_meta.exists():
            self._state_meta.write_text(json.dumps({"structured_offset": 0}, indent=2), encoding="utf-8")

    async def get_pinned(self) -> list[dict]:
        try:
            return json.loads(self._pinned.read_text(encoding="utf-8"))
        except Exception:
            return []

    async def set_pinned(self, items: list[dict]) -> None:
        self._pinned.write_text(json.dumps(items, indent=2, ensure_ascii=False), encoding="utf-8")

    async def add_pinned(self, item: dict) -> bool:
        """
        Add a pinned memory item if not already present (by exact content match).
        Returns True if added.
        """
        items = await self.get_pinned()
        content = str(item.get("content", "")).strip()
        if content and any(str(x.get("content", "")).strip() == content for x in items if isinstance(x, dict)):
            return False
        items.append(item)
        await self.set_pinned(items)
        return True

    async def observe_turn(self, *, run_id: str, user_text: str, assistant_text: str) -> None:
        """
        Deprecated: episodic history is derived from events.jsonl.
        Kept as a no-op for compatibility.
        """
        return

    async def save_structured_memories(
        self,
        *,
        run_id: str,
        memories: List[Dict[str, Any]],
    ) -> int:
        """
        Append extracted structured memories to memories.jsonl.
        Returns number of memories written.
        """
        written = 0
        now_ms = int(time.time() * 1000)
        with self._structured.open("a", encoding="utf-8") as f:
            for i, m in enumerate(memories):
                rec = {
                    "id": f"mem_{now_ms}_{i}",
                    "runId": run_id,
                    "timestamp_ms": now_ms,
                    **m,
                }
                f.write(json.dumps(rec, ensure_ascii=False) + "\n")
                written += 1
        return written

    def _load_state(self) -> Dict[str, Any]:
        try:
            return json.loads(self._state.read_text(encoding="utf-8"))
        except Exception:
            return {}

    def _save_state(self, state: Dict[str, Any]) -> None:
        self._state.write_text(json.dumps(state, indent=2, ensure_ascii=False), encoding="utf-8")

    def _load_meta(self) -> Dict[str, Any]:
        try:
            return json.loads(self._state_meta.read_text(encoding="utf-8"))
        except Exception:
            return {"structured_offset": 0}

    def _save_meta(self, meta: Dict[str, Any]) -> None:
        self._state_meta.write_text(json.dumps(meta, indent=2, ensure_ascii=False), encoding="utf-8")

    def _fingerprint(self, mem_type: str, content: str) -> str:
        norm = " ".join((content or "").strip().lower().split())
        raw = f"{mem_type}:{norm}".encode("utf-8")
        return hashlib.sha256(raw).hexdigest()[:16]

    async def consolidate(self) -> int:
        """
        Incrementally consolidate extracted memory candidates (memories.jsonl) into memory_state.json.
        Returns number of new unique items added.
        """
        meta = self._load_meta()
        offset = int(meta.get("structured_offset", 0) or 0)
        state = self._load_state()

        added = 0
        with self._structured.open("r", encoding="utf-8") as f:
            f.seek(offset)
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    rec = json.loads(line)
                except Exception:
                    continue

                mem_type = str(rec.get("type", "") or "").strip()
                content = str(rec.get("content", "") or "").strip()
                if not mem_type or not content:
                    continue

                fp = self._fingerprint(mem_type, content)
                now_ms = int(time.time() * 1000)
                ts = int(rec.get("timestamp_ms", now_ms) or now_ms)

                existing = state.get(fp)
                if not isinstance(existing, dict):
                    existing = {
                        "id": fp,
                        "type": mem_type,
                        "content": content,
                        "importance": int(rec.get("importance", 0) or 0),
                        "tags": list(rec.get("tags") or []),
                        "context": str(rec.get("context", "") or "").strip(),
                        "first_seen_ms": ts,
                        "last_seen_ms": ts,
                        "runIds": [],
                        "count": 0,
                    }
                    state[fp] = existing
                    added += 1

                existing["importance"] = max(int(existing.get("importance", 0) or 0), int(rec.get("importance", 0) or 0))
                tags = set(existing.get("tags") or [])
                tags.update(rec.get("tags") or [])
                existing["tags"] = sorted(tags)
                ctx = str(existing.get("context", "") or "").strip()
                new_ctx = str(rec.get("context", "") or "").strip()
                if not ctx and new_ctx:
                    existing["context"] = new_ctx
                if new_ctx:
                    existing["last_context"] = new_ctx
                existing["last_seen_ms"] = max(int(existing.get("last_seen_ms", 0) or 0), ts)

                rid = rec.get("runId")
                if isinstance(rid, str) and rid:
                    run_ids = set(existing.get("runIds") or [])
                    if rid not in run_ids:
                        run_ids.add(rid)
                        existing["runIds"] = sorted(run_ids)
                existing["count"] = int(existing.get("count", 0) or 0) + 1

            offset = f.tell()

        meta["structured_offset"] = offset
        self._save_state(state)
        self._save_meta(meta)
        return added

    async def search_structured(self, query: str, limit: int = 5) -> list[dict]:
        """
        Keyword scan over consolidated memory_state.json.
        """
        q = (query or "").lower().strip()
        if not q:
            return []

        scored: List[Tuple[float, dict]] = []
        state = self._load_state()
        for rec in state.values():
            if not isinstance(rec, dict):
                continue
            hay = " ".join(
                [
                    str(rec.get("type", "")),
                    str(rec.get("content", "")),
                    str(rec.get("context", "")),
                    " ".join(rec.get("tags", []) or []),
                ]
            ).lower()
            if q in hay:
                importance = float(rec.get("importance", 0) or 0)
                scored.append((importance, rec))

        scored.sort(key=lambda x: x[0], reverse=True)
        return [r for _, r in scored[:limit]]
