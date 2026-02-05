from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any, Dict, List

from .paths import data_dir
from .jsonl_archive import rotate_jsonl, prune_archives
from .memory_db import MemoryDB
from agent_blob import config


class MemoryStore:
    """
    V2 memory:
    - pinned.json: small curated list (always loaded)
    - memories.jsonl: append-only extracted memory candidates
    - agent_blob.sqlite: consolidated, deduped memory state (SQLite + FTS5 + optional embeddings)

    All retrieval/indexing is intentionally minimal here; this is designed
    to be swapped with BM25 + embeddings later without changing the runtime API.
    """

    def __init__(self):
        d = data_dir()
        self._pinned = d / "pinned.json"
        self._structured = d / "memories.jsonl"
        self._db_path = d / "agent_blob.sqlite"
        self._db = MemoryDB(self._db_path)
        # Legacy files (kept for one-way migration if present)
        self._legacy_state = d / "memory_state.json"

    async def startup(self) -> None:
        self._pinned.parent.mkdir(parents=True, exist_ok=True)
        if not self._pinned.exists():
            self._pinned.write_text("[]", encoding="utf-8")
        if not self._structured.exists():
            self._structured.write_text("", encoding="utf-8")
        self._db.startup()
        await self._maybe_migrate_legacy()

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
        Also upsert into the SQLite consolidated memory state.
        Returns number of memories written to the candidate log.
        """
        # Upsert into consolidated store first (dedup happens here).
        self._db.upsert_many(run_id=run_id, memories=memories)

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

    async def consolidate(self) -> int:
        """
        Deprecated: consolidation is handled by SQLite upserts during save_structured_memories().
        Returns 0.
        """
        return 0

    async def search_structured(self, query: str, limit: int = 5) -> list[dict]:
        """
        Hybrid retrieval over consolidated SQLite memory state:
        - BM25 (FTS5)
        - importance + recency
        - optional vector similarity (if embeddings exist)
        """
        q = (query or "").strip()
        if not q:
            return []
        return self._db.search_hybrid(query=q, limit=int(limit), query_embedding=None)

    async def list_recent_structured(self, *, limit: int = 20) -> list[dict]:
        return self._db.list_recent(limit=int(limit))

    async def delete_structured(self, *, memory_id: str) -> dict:
        ok = self._db.delete_by_fingerprint(memory_id)
        return {"ok": ok, "id": memory_id}

    async def search_structured_hybrid(self, *, query: str, limit: int, llm: Any | None = None) -> list[dict]:
        """
        Union hybrid retrieval:
        - BM25 candidates from SQLite FTS5
        - Vector candidates by scanning recent embedded items (bounded; no vector DB required)
        - Union candidates then rerank by combined score (lexical + vector + importance + recency)
        """
        q = (query or "").strip()
        if not q:
            return []
        bm = self._db.search_bm25(q, limit=50)

        query_embedding = None
        vec: list[tuple[int, float]] = []
        if llm is not None and config.memory_embeddings_enabled():
            try:
                model = config.memory_embedding_model()
                vecs = await llm.embed(model=model, texts=[q])
                if vecs and isinstance(vecs[0], list) and vecs[0]:
                    query_embedding = vecs[0]
                    vec = self._db.vector_candidates(
                        query_embedding=query_embedding,
                        scan_limit=config.memory_vector_scan_limit(),
                        top_k=config.memory_vector_top_k(),
                    )
            except Exception:
                query_embedding = None
                vec = []

        if not bm and not vec:
            return []

        return self._db.search_hybrid_union(bm=bm, vec=vec, limit=int(limit), query_embedding=query_embedding)

    async def embed_pending(self, *, llm: Any, limit: int) -> int:
        """
        Best-effort background embedding refresh for memory items marked missing/dirty.
        """
        if not config.memory_embeddings_enabled():
            return 0
        pending = self._db.pending_embeddings(limit=int(limit))
        if not pending:
            return 0
        model = config.memory_embedding_model()
        texts = [p["text"] for p in pending]
        vecs = await llm.embed(model=model, texts=texts)
        if not vecs or len(vecs) != len(pending):
            return 0
        rows = [(int(pending[i]["rowid"]), vecs[i]) for i in range(len(pending))]
        return self._db.write_embeddings(rows=rows, model=model)

    async def rotate_and_prune_candidates(self) -> Dict[str, Any]:
        """
        Rotate memories.jsonl (structured candidates) and prune archives.

        Note: the candidate log is optional/audit-only; rotation is independent of retrieval.
        """
        d = self._pinned.parent
        rec = rotate_jsonl(
            data_dir=d,
            kind="memories",
            active_path=self._structured,
            max_bytes=config.log_max_bytes("memories", 5_000_000),
        )

        pruned = prune_archives(
            data_dir=d,
            kind="memories",
            keep_days=config.log_keep_days("memories", 30),
            keep_max_files=config.log_keep_max_files("memories", 50),
        )
        return {"rotated": bool(rec), "pruned": pruned}

    async def _maybe_migrate_legacy(self) -> None:
        """
        One-way migration from legacy memory_state.json into SQLite.
        Safe to call repeatedly: SQLite upsert dedups by fingerprint.
        """
        try:
            if not self._legacy_state.exists():
                return
            if self._db.count_items() > 0:
                return
            obj = json.loads(self._legacy_state.read_text(encoding="utf-8"))
            if not isinstance(obj, dict):
                return
            memories: List[Dict[str, Any]] = []
            for rec in obj.values():
                if not isinstance(rec, dict):
                    continue
                memories.append(
                    {
                        "type": rec.get("type", ""),
                        "content": rec.get("content", ""),
                        "context": rec.get("context", ""),
                        "importance": rec.get("importance", 0),
                        "tags": rec.get("tags", []),
                    }
                )
            if memories:
                self._db.upsert_many(run_id="migration", memories=memories)
        except Exception:
            return
