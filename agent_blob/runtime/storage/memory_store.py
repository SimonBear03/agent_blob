from __future__ import annotations

import json
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List

from .paths import data_dir


class MemoryStore:
    """
    V2 skeleton memory:
    - pinned.json: small curated list (always loaded)
    - memory.jsonl: append-only “archival” memory items

    All retrieval/indexing is intentionally minimal here; this is designed
    to be swapped with BM25 + embeddings later without changing the runtime API.
    """

    def __init__(self):
        d = data_dir()
        self._pinned = d / "pinned.json"
        self._archival = d / "memory.jsonl"

    async def startup(self) -> None:
        self._pinned.parent.mkdir(parents=True, exist_ok=True)
        if not self._pinned.exists():
            self._pinned.write_text("[]", encoding="utf-8")
        if not self._archival.exists():
            self._archival.write_text("", encoding="utf-8")

    async def get_pinned(self) -> list[dict]:
        try:
            return json.loads(self._pinned.read_text(encoding="utf-8"))
        except Exception:
            return []

    async def set_pinned(self, items: list[dict]) -> None:
        self._pinned.write_text(json.dumps(items, indent=2, ensure_ascii=False), encoding="utf-8")

    async def observe_turn(self, *, run_id: str, user_text: str, assistant_text: str) -> None:
        # Placeholder for extraction + consolidation:
        # For now, append a simple episodic record.
        rec = {
            "id": f"mem_{int(time.time()*1000)}",
            "type": "episodic",
            "runId": run_id,
            "text": user_text,
        }
        with self._archival.open("a", encoding="utf-8") as f:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")

    async def search(self, query: str, limit: int = 5) -> list[dict]:
        # Minimal keyword scan over archival JSONL.
        q = (query or "").lower().strip()
        if not q:
            return []
        hits: list[dict] = []
        try:
            with self._archival.open("r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        rec = json.loads(line)
                    except Exception:
                        continue
                    txt = str(rec.get("text", "")).lower()
                    if q in txt:
                        hits.append(rec)
                        if len(hits) >= limit:
                            break
        except FileNotFoundError:
            return []
        return hits
