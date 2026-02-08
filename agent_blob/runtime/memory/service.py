from __future__ import annotations

import json
import time
from typing import Any, Dict, List
from pathlib import Path

from agent_blob import config
from agent_blob.runtime.memory.extractor import MemoryExtractor
from agent_blob.runtime.storage.memory_db import MemoryDB
from agent_blob.runtime.storage.paths import memory_dir, data_dir
from agent_blob.runtime.storage.jsonl_archive import rotate_jsonl, prune_archives


class MemoryService:
    """
    Canonical V3 memory service:
    - pinned.json as small always-load memory
    - SQLite memory_items (MemoryDB) as long-term canonical memory
    - embeddings/FTS are derived indexes managed inside MemoryDB
    """

    def __init__(self):
        d = memory_dir()
        self._memory_dir = d
        self._legacy_data_dir = data_dir()
        self._pinned_path = d / "pinned.json"
        self._audit_path = d / "memory_events.jsonl"
        self._db_path = d / "agent_blob.sqlite"
        self._db = MemoryDB(self._db_path)
        self._extractor = MemoryExtractor()

    async def startup(self) -> None:
        self._migrate_legacy_files()
        self._pinned_path.parent.mkdir(parents=True, exist_ok=True)
        if not self._pinned_path.exists():
            self._pinned_path.write_text("[]", encoding="utf-8")
        if not self._audit_path.exists():
            self._audit_path.write_text("", encoding="utf-8")
        self._db.startup()

    async def get_pinned(self) -> List[Dict[str, Any]]:
        try:
            items = json.loads(self._pinned_path.read_text(encoding="utf-8"))
        except Exception:
            return []
        return items if isinstance(items, list) else []

    async def set_pinned(self, items: List[Dict[str, Any]]) -> None:
        self._pinned_path.write_text(json.dumps(items, indent=2, ensure_ascii=False), encoding="utf-8")
        await self._append_audit(
            {
                "action": "modified",
                "entity": "pinned",
                "count": len(items),
            }
        )

    async def add_pinned(self, item: Dict[str, Any]) -> bool:
        content = str(item.get("content", "") or "").strip()
        if not content:
            return False
        existing = await self.get_pinned()
        if any(isinstance(x, dict) and str(x.get("content", "")).strip() == content for x in existing):
            return False
        existing.append(item)
        await self.set_pinned(existing)
        await self._append_audit(
            {
                "action": "added",
                "entity": "pinned",
                "content": content,
            }
        )
        return True

    async def ingest_turn(self, *, run_id: str, user_text: str, assistant_text: str, llm: Any | None) -> Dict[str, Any]:
        """
        Extract and upsert long-term memories from one completed turn.
        """
        if llm is None:
            return {"structured_written": 0, "error": "llm_unavailable"}
        try:
            memories = await self._extractor.extract(llm=llm, user_text=user_text, assistant_text=assistant_text)
            if not memories:
                return {"structured_written": 0, "error": None}
            detail = self._db.upsert_many_detailed(run_id=run_id, memories=memories)
            for item in detail.get("added", []):
                await self._append_audit(
                    {
                        "action": "added",
                        "entity": "memory",
                        "run_id": run_id,
                        "memory": item,
                    }
                )
            for item in detail.get("modified", []):
                await self._append_audit(
                    {
                        "action": "modified",
                        "entity": "memory",
                        "run_id": run_id,
                        "memory": item,
                    }
                )
            return {"structured_written": int(detail.get("touched", 0)), "error": None}
        except Exception as exc:
            return {"structured_written": 0, "error": str(exc)}

    async def search(self, *, query: str, limit: int = 5, llm: Any | None = None) -> List[Dict[str, Any]]:
        q = (query or "").strip()
        if not q:
            return []
        if llm is not None and config.memory_embeddings_enabled():
            try:
                em = await llm.embed(model=config.memory_embedding_model(), texts=[q])
                query_embedding = em[0] if em and isinstance(em[0], list) else None
            except Exception:
                query_embedding = None
        else:
            query_embedding = None
        return self._db.search_hybrid(query=q, limit=int(limit), query_embedding=query_embedding)

    async def list_recent(self, *, limit: int = 20) -> List[Dict[str, Any]]:
        return self._db.list_recent(limit=int(limit))

    async def delete(self, *, memory_id: str, run_id: str | None = None) -> Dict[str, Any]:
        before = self._db.get_by_fingerprint(memory_id)
        ok = self._db.delete_by_fingerprint(memory_id)
        if ok:
            await self._append_audit(
                {
                    "action": "removed",
                    "entity": "memory",
                    "run_id": run_id,
                    "memory": before or {"id": memory_id},
                }
            )
        return {"ok": bool(ok), "id": memory_id}

    async def embed_pending(self, *, llm: Any, limit: int) -> int:
        if not config.memory_embeddings_enabled():
            return 0
        pending = self._db.pending_embeddings(limit=int(limit))
        if not pending:
            return 0
        model = config.memory_embedding_model()
        texts = [p["text"] for p in pending]
        vectors = await llm.embed(model=model, texts=texts)
        if not vectors or len(vectors) != len(pending):
            return 0
        rows = [(int(pending[i]["rowid"]), vectors[i]) for i in range(len(pending))]
        return self._db.write_embeddings(rows=rows, model=model)

    def _migrate_legacy_files(self) -> None:
        """
        One-way file migration from legacy ./data memory files to ./memory.
        """
        self._memory_dir.mkdir(parents=True, exist_ok=True)
        # pinned.json
        legacy_pinned = self._legacy_data_dir / "pinned.json"
        if legacy_pinned.exists() and (not self._pinned_path.exists()):
            try:
                legacy_pinned.replace(self._pinned_path)
            except Exception:
                pass

        # SQLite + sidecars (if target DB does not exist yet).
        legacy_db = self._legacy_data_dir / "agent_blob.sqlite"
        if legacy_db.exists() and (not self._db_path.exists()):
            for suffix in ("", "-wal", "-shm"):
                src = Path(str(legacy_db) + suffix)
                dst = Path(str(self._db_path) + suffix)
                if src.exists():
                    try:
                        src.replace(dst)
                    except Exception:
                        pass

        # Move deprecated candidate log out of data/ to avoid confusion.
        legacy_candidates = self._legacy_data_dir / "memories.jsonl"
        if legacy_candidates.exists():
            target_archives = self._memory_dir / "archives"
            target_archives.mkdir(parents=True, exist_ok=True)
            target = target_archives / "memories_legacy.jsonl"
            if not target.exists():
                try:
                    legacy_candidates.replace(target)
                except Exception:
                    pass

    async def rotate_and_prune_audit(self) -> Dict[str, Any]:
        rec = rotate_jsonl(
            data_dir=self._memory_dir,
            kind="memory_events",
            active_path=self._audit_path,
            max_bytes=config.log_max_bytes("memory_events", 5_000_000),
        )
        pruned = prune_archives(
            data_dir=self._memory_dir,
            kind="memory_events",
            keep_days=config.log_keep_days("memory_events", 30),
            keep_max_files=config.log_keep_max_files("memory_events", 50),
        )
        return {"rotated": bool(rec), "pruned": pruned}

    async def _append_audit(self, event: Dict[str, Any]) -> None:
        rec = {
            "ts_ms": int(time.time() * 1000),
            **event,
        }
        with self._audit_path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")
