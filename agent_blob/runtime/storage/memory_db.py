from __future__ import annotations

import json
import sqlite3
import time
import hashlib
import struct
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple


def _fingerprint(mem_type: str, content: str) -> str:
    norm = " ".join((content or "").strip().lower().split())
    raw = f"{mem_type}:{norm}".encode("utf-8")
    return hashlib.sha256(raw).hexdigest()[:32]


def _pack_f32(vec: List[float]) -> bytes:
    return struct.pack(f"<{len(vec)}f", *[float(x) for x in vec])


def _unpack_f32(blob: bytes) -> List[float]:
    if not blob:
        return []
    n = len(blob) // 4
    return list(struct.unpack(f"<{n}f", blob[: n * 4]))


def _cosine(a: List[float], b: List[float]) -> float:
    if not a or not b or len(a) != len(b):
        return 0.0
    dot = 0.0
    na = 0.0
    nb = 0.0
    for x, y in zip(a, b):
        dot += x * y
        na += x * x
        nb += y * y
    if na <= 0.0 or nb <= 0.0:
        return 0.0
    return float(dot / ((na ** 0.5) * (nb ** 0.5)))


@dataclass
class MemoryRow:
    fingerprint: str
    type: str
    content: str
    context: str
    importance: int
    tags: List[str]
    first_seen_ms: int
    last_seen_ms: int
    count: int
    last_run_id: str
    embedding_status: str


class MemoryDB:
    """
    SQLite-backed consolidated long-term memory state with:
    - memory_items table (deduped by fingerprint)
    - FTS5 table for BM25 lexical search
    - optional embeddings stored as float32 blobs (no sqlite extension required)
    """

    def __init__(self, path: Path):
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._con: sqlite3.Connection | None = None

    def _connect(self) -> sqlite3.Connection:
        if self._con is None:
            con = sqlite3.connect(str(self.path))
            con.row_factory = sqlite3.Row
            con.execute("PRAGMA journal_mode=WAL")
            con.execute("PRAGMA synchronous=NORMAL")
            con.execute("PRAGMA temp_store=MEMORY")
            self._con = con
        return self._con

    def close(self) -> None:
        if self._con is not None:
            try:
                self._con.close()
            finally:
                self._con = None

    def startup(self) -> None:
        con = self._connect()
        con.execute(
            """
            CREATE TABLE IF NOT EXISTS memory_items (
              rowid INTEGER PRIMARY KEY,
              fingerprint TEXT NOT NULL UNIQUE,
              type TEXT NOT NULL,
              content TEXT NOT NULL,
              context TEXT NOT NULL DEFAULT '',
              importance INTEGER NOT NULL DEFAULT 0,
              tags_json TEXT NOT NULL DEFAULT '[]',
              first_seen_ms INTEGER NOT NULL,
              last_seen_ms INTEGER NOT NULL,
              count INTEGER NOT NULL DEFAULT 0,
              last_run_id TEXT NOT NULL DEFAULT '',
              embedding BLOB,
              embedding_model TEXT NOT NULL DEFAULT '',
              embedding_updated_ms INTEGER NOT NULL DEFAULT 0,
              embedding_status TEXT NOT NULL DEFAULT 'missing'
            )
            """
        )
        # FTS5 for BM25 lexical search.
        con.execute(
            """
            CREATE VIRTUAL TABLE IF NOT EXISTS memory_fts
            USING fts5(content, context, tags, content='memory_items', content_rowid='rowid')
            """
        )
        # Triggers to keep FTS in sync.
        con.executescript(
            """
            CREATE TRIGGER IF NOT EXISTS memory_items_ai AFTER INSERT ON memory_items BEGIN
              INSERT INTO memory_fts(rowid, content, context, tags)
              VALUES (new.rowid, new.content, new.context, new.tags_json);
            END;
            CREATE TRIGGER IF NOT EXISTS memory_items_ad AFTER DELETE ON memory_items BEGIN
              INSERT INTO memory_fts(memory_fts, rowid, content, context, tags)
              VALUES('delete', old.rowid, old.content, old.context, old.tags_json);
            END;
            CREATE TRIGGER IF NOT EXISTS memory_items_au AFTER UPDATE ON memory_items BEGIN
              INSERT INTO memory_fts(memory_fts, rowid, content, context, tags)
              VALUES('delete', old.rowid, old.content, old.context, old.tags_json);
              INSERT INTO memory_fts(rowid, content, context, tags)
              VALUES (new.rowid, new.content, new.context, new.tags_json);
            END;
            """
        )
        con.commit()

    def count_items(self) -> int:
        con = self._connect()
        cur = con.execute("SELECT COUNT(*) AS n FROM memory_items")
        row = cur.fetchone()
        return int(row["n"] if row else 0)

    def delete_by_fingerprint(self, fingerprint: str) -> bool:
        fp = str(fingerprint or "").strip()
        if not fp:
            return False
        con = self._connect()
        cur = con.execute("DELETE FROM memory_items WHERE fingerprint = ?", (fp,))
        con.commit()
        return cur.rowcount > 0

    def list_recent(self, limit: int = 20) -> List[Dict[str, Any]]:
        con = self._connect()
        cur = con.execute(
            """
            SELECT fingerprint, type, content, context, importance, tags_json, last_seen_ms, count
            FROM memory_items
            ORDER BY last_seen_ms DESC
            LIMIT ?
            """,
            (int(limit),),
        )
        out: List[Dict[str, Any]] = []
        for r in cur.fetchall():
            try:
                tags = json.loads(r["tags_json"] or "[]")
            except Exception:
                tags = []
            out.append(
                {
                    "id": str(r["fingerprint"]),
                    "type": str(r["type"]),
                    "content": str(r["content"]),
                    "context": str(r["context"]),
                    "importance": int(r["importance"] or 0),
                    "tags": list(tags or []),
                    "last_seen_ms": int(r["last_seen_ms"] or 0),
                    "count": int(r["count"] or 0),
                }
            )
        return out

    def upsert_many(self, *, run_id: str, memories: List[Dict[str, Any]]) -> int:
        """
        Upsert (dedup) extracted memories into memory_items.
        Returns number of rows inserted or updated.
        """
        if not memories:
            return 0

        con = self._connect()
        now_ms = int(time.time() * 1000)
        touched = 0

        for m in memories:
            mem_type = str(m.get("type", "") or "").strip()
            content = str(m.get("content", "") or "").strip()
            if not mem_type or not content:
                continue
            context = str(m.get("context", "") or "").strip()
            importance = int(m.get("importance", 0) or 0)
            tags = list(m.get("tags") or [])
            tags_json = json.dumps(sorted({str(t) for t in tags if str(t).strip()}), ensure_ascii=False)
            fp = _fingerprint(mem_type, content)

            # Insert or update.
            # If content/context/tags/type changes, embedding is marked dirty.
            cur = con.execute("SELECT rowid, type, content, context, tags_json FROM memory_items WHERE fingerprint = ?", (fp,))
            row = cur.fetchone()
            if row is None:
                con.execute(
                    """
                    INSERT INTO memory_items
                      (fingerprint, type, content, context, importance, tags_json, first_seen_ms, last_seen_ms, count, last_run_id, embedding_status)
                    VALUES
                      (?, ?, ?, ?, ?, ?, ?, ?, 1, ?, 'missing')
                    """,
                    (fp, mem_type, content, context, importance, tags_json, now_ms, now_ms, run_id),
                )
                touched += 1
            else:
                existing_changed = (
                    str(row["type"]) != mem_type
                    or str(row["content"]) != content
                    or str(row["context"]) != context
                    or str(row["tags_json"]) != tags_json
                )
                # importance: max; tags: union; context: keep if existing empty
                # For simplicity, we keep the new context only if old context is empty.
                old_ctx = str(row["context"] or "")
                merged_ctx = old_ctx if old_ctx.strip() else context
                # Merge tags by set union (row tags_json already sorted json list)
                try:
                    old_tags = set(json.loads(str(row["tags_json"] or "[]")) or [])
                except Exception:
                    old_tags = set()
                try:
                    new_tags = set(json.loads(tags_json) or [])
                except Exception:
                    new_tags = set()
                merged_tags_json = json.dumps(sorted(old_tags | new_tags), ensure_ascii=False)

                con.execute(
                    """
                    UPDATE memory_items
                    SET
                      last_seen_ms = ?,
                      count = count + 1,
                      importance = CASE WHEN importance > ? THEN importance ELSE ? END,
                      context = ?,
                      tags_json = ?,
                      last_run_id = ?,
                      embedding_status = CASE
                        WHEN ? THEN 'dirty'
                        ELSE embedding_status
                      END
                    WHERE fingerprint = ?
                    """,
                    (now_ms, importance, importance, merged_ctx, merged_tags_json, run_id, 1 if existing_changed else 0, fp),
                )
                touched += 1

        con.commit()
        return touched

    def fetch_by_rowids(self, rowids: List[int]) -> List[Dict[str, Any]]:
        # Not used by the runtime currently; keep as a simple helper.
        if not rowids:
            return []
        con = self._connect()
        q = ",".join(["?"] * len(rowids))
        cur = con.execute(
            f"SELECT rowid, fingerprint, type, content, context, importance, tags_json, first_seen_ms, last_seen_ms, count FROM memory_items WHERE rowid IN ({q})",
            tuple(rowids),
        )
        out: List[Dict[str, Any]] = []
        for r in cur.fetchall():
            try:
                tags = json.loads(r["tags_json"] or "[]")
            except Exception:
                tags = []
            out.append(
                {
                    "rowid": int(r["rowid"]),
                    "id": str(r["fingerprint"]),
                    "type": str(r["type"]),
                    "content": str(r["content"]),
                    "context": str(r["context"]),
                    "importance": int(r["importance"] or 0),
                    "tags": list(tags or []),
                    "first_seen_ms": int(r["first_seen_ms"] or 0),
                    "last_seen_ms": int(r["last_seen_ms"] or 0),
                    "count": int(r["count"] or 0),
                }
            )
        return out

    def search_bm25(self, query: str, limit: int = 50) -> List[Tuple[int, float]]:
        """
        Return list of (rowid, bm25_score) where lower bm25 is better.
        """
        q = (query or "").strip()
        if not q:
            return []
        con = self._connect()
        try:
            cur = con.execute(
                """
                SELECT rowid, bm25(memory_fts) AS score
                FROM memory_fts
                WHERE memory_fts MATCH ?
                ORDER BY score
                LIMIT ?
                """,
                (q, int(limit)),
            )
            return [(int(r["rowid"]), float(r["score"])) for r in cur.fetchall()]
        except Exception:
            # Fallback: simple LIKE scan
            cur = con.execute(
                """
                SELECT rowid, 1.0 AS score FROM memory_items
                WHERE content LIKE ? OR context LIKE ?
                ORDER BY last_seen_ms DESC
                LIMIT ?
                """,
                (f"%{q}%", f"%{q}%", int(limit)),
            )
            return [(int(r["rowid"]), float(r["score"])) for r in cur.fetchall()]

    def vector_candidates(
        self,
        *,
        query_embedding: List[float],
        scan_limit: int = 2000,
        top_k: int = 50,
    ) -> List[Tuple[int, float]]:
        """
        Vector candidate generation without a dedicated vector index:
        - scan the most recent items with embeddings (bounded by scan_limit)
        - compute cosine similarity
        - return top_k (rowid, sim)
        """
        if not query_embedding:
            return []
        scan_limit = max(0, int(scan_limit or 0))
        top_k = max(0, int(top_k or 0))
        if scan_limit <= 0 or top_k <= 0:
            return []

        con = self._connect()
        cur = con.execute(
            """
            SELECT rowid, embedding
            FROM memory_items
            WHERE embedding IS NOT NULL AND length(embedding) > 0
            ORDER BY last_seen_ms DESC
            LIMIT ?
            """,
            (scan_limit,),
        )
        scored: List[Tuple[float, int]] = []
        for r in cur.fetchall():
            blob = r["embedding"]
            if not blob:
                continue
            vec = _unpack_f32(blob)
            sim = _cosine(query_embedding, vec)
            if sim > 0:
                scored.append((sim, int(r["rowid"])))
        scored.sort(key=lambda x: x[0], reverse=True)
        return [(rid, sim) for sim, rid in scored[:top_k]]

    def get_embedding_candidates(self, rowids: List[int]) -> Dict[int, List[float]]:
        if not rowids:
            return {}
        con = self._connect()
        q = ",".join(["?"] * len(rowids))
        cur = con.execute(f"SELECT rowid, embedding FROM memory_items WHERE rowid IN ({q})", tuple(rowids))
        out: Dict[int, List[float]] = {}
        for r in cur.fetchall():
            blob = r["embedding"]
            if blob:
                out[int(r["rowid"])] = _unpack_f32(blob)
        return out

    def mark_embedding_dirty(self, rowid: int) -> None:
        con = self._connect()
        con.execute("UPDATE memory_items SET embedding_status='dirty' WHERE rowid=?", (int(rowid),))
        con.commit()

    def pending_embeddings(self, limit: int = 50) -> List[Dict[str, Any]]:
        con = self._connect()
        cur = con.execute(
            """
            SELECT rowid, type, content, context, tags_json
            FROM memory_items
            WHERE embedding_status IN ('missing','dirty')
            ORDER BY last_seen_ms DESC
            LIMIT ?
            """,
            (int(limit),),
        )
        out = []
        for r in cur.fetchall():
            out.append(
                {
                    "rowid": int(r["rowid"]),
                    "text": " ".join(
                        [
                            str(r["type"] or ""),
                            str(r["content"] or ""),
                            str(r["context"] or ""),
                            str(r["tags_json"] or ""),
                        ]
                    ).strip(),
                }
            )
        return out

    def write_embeddings(self, *, rows: List[Tuple[int, List[float]]], model: str) -> int:
        if not rows:
            return 0
        con = self._connect()
        now_ms = int(time.time() * 1000)
        for rowid, vec in rows:
            con.execute(
                """
                UPDATE memory_items
                SET embedding=?, embedding_model=?, embedding_updated_ms=?, embedding_status='fresh'
                WHERE rowid=?
                """,
                (_pack_f32(vec), model, now_ms, int(rowid)),
            )
        con.commit()
        return len(rows)

    def search_hybrid(
        self,
        *,
        query: str,
        limit: int,
        query_embedding: Optional[List[float]] = None,
        candidate_limit: int = 50,
    ) -> List[Dict[str, Any]]:
        """
        Hybrid retrieval:
        - BM25 candidates (lexical)
        - then rerank by importance + recency + optional vector similarity
        """
        bm = self.search_bm25(query, limit=candidate_limit)
        if not bm:
            return []
        return self.search_hybrid_from_bm25(bm=bm, limit=limit, query_embedding=query_embedding)

    def search_hybrid_union(
        self,
        *,
        bm: List[Tuple[int, float]],
        vec: List[Tuple[int, float]],
        limit: int,
        query_embedding: Optional[List[float]] = None,
    ) -> List[Dict[str, Any]]:
        """
        Union hybrid reranking for candidates coming from BM25 and vector search.
        bm: list[(rowid, bm25_score)] where smaller is better
        vec: list[(rowid, sim)] where larger is better
        """
        # Union rowids; keep scores for reranking.
        bm_by = {int(rid): float(score) for rid, score in (bm or [])}
        vec_by = {int(rid): float(sim) for rid, sim in (vec or [])}
        rowids = list({*bm_by.keys(), *vec_by.keys()})
        if not rowids:
            return []

        con = self._connect()
        q = ",".join(["?"] * len(rowids))
        cur = con.execute(
            f"""
            SELECT rowid, fingerprint, type, content, context, importance, tags_json, last_seen_ms, count, embedding
            FROM memory_items
            WHERE rowid IN ({q})
            """,
            tuple(rowids),
        )
        now_ms = int(time.time() * 1000)
        by_rowid: Dict[int, sqlite3.Row] = {int(r["rowid"]): r for r in cur.fetchall()}

        scored: List[Tuple[float, int]] = []
        for rid in rowids:
            r = by_rowid.get(rid)
            if not r:
                continue

            bm25 = bm_by.get(rid)
            lexical = 0.0
            if bm25 is not None:
                lexical = max(0.0, 2.0 - min(2.0, abs(float(bm25))))

            importance = float(r["importance"] or 0)
            last_seen = float(r["last_seen_ms"] or 0)
            age_days = max(0.0, (now_ms - last_seen) / 86_400_000.0) if last_seen else 3650.0
            recency = max(0.0, 1.5 - min(1.5, age_days / 7.0))

            vec_sim = vec_by.get(rid, 0.0)
            if query_embedding is not None and vec_sim <= 0.0:
                blob = r["embedding"]
                if blob:
                    vec_sim = _cosine(query_embedding, _unpack_f32(blob))

            score = (lexical * 3.0) + (importance * 2.0) + recency + (vec_sim * 4.0)
            scored.append((score, rid))

        scored.sort(key=lambda x: x[0], reverse=True)
        top = [rid for _, rid in scored[: int(limit)]]

        out: List[Dict[str, Any]] = []
        for rid in top:
            r = by_rowid.get(rid)
            if not r:
                continue
            try:
                tags = json.loads(r["tags_json"] or "[]")
            except Exception:
                tags = []
            out.append(
                {
                    "id": str(r["fingerprint"]),
                    "type": str(r["type"]),
                    "content": str(r["content"]),
                    "context": str(r["context"]),
                    "importance": int(r["importance"] or 0),
                    "tags": list(tags or []),
                    "last_seen_ms": int(r["last_seen_ms"] or 0),
                    "count": int(r["count"] or 0),
                }
            )
        return out

    def search_hybrid_from_bm25(
        self,
        *,
        bm: List[Tuple[int, float]],
        limit: int,
        query_embedding: Optional[List[float]] = None,
    ) -> List[Dict[str, Any]]:
        """
        Rerank an existing BM25 candidate list. This lets callers avoid embedding the query
        until they know lexical candidates exist.
        """
        if not bm:
            return []

        rowids = [rid for rid, _ in bm]
        con = self._connect()
        q = ",".join(["?"] * len(rowids))
        cur = con.execute(
            f"""
            SELECT rowid, fingerprint, type, content, context, importance, tags_json, last_seen_ms, count, embedding
            FROM memory_items
            WHERE rowid IN ({q})
            """,
            tuple(rowids),
        )
        now_ms = int(time.time() * 1000)
        by_rowid: Dict[int, sqlite3.Row] = {int(r["rowid"]): r for r in cur.fetchall()}

        # Prepare vector candidates
        vecs: Dict[int, List[float]] = {}
        if query_embedding:
            for rid in rowids:
                r = by_rowid.get(rid)
                if not r:
                    continue
                blob = r["embedding"]
                if blob:
                    vecs[rid] = _unpack_f32(blob)

        scored: List[Tuple[float, int]] = []
        bm_by = {rid: score for rid, score in bm}
        for rid in rowids:
            r = by_rowid.get(rid)
            if not r:
                continue
            bm25 = float(bm_by.get(rid, 1.0))
            lexical = max(0.0, 2.0 - min(2.0, abs(bm25)))  # invert-ish; smaller |bm25| -> bigger score
            importance = float(r["importance"] or 0)
            last_seen = float(r["last_seen_ms"] or 0)
            age_days = max(0.0, (now_ms - last_seen) / 86_400_000.0) if last_seen else 3650.0
            recency = max(0.0, 1.5 - min(1.5, age_days / 7.0))
            vec_sim = _cosine(query_embedding, vecs.get(rid, [])) if query_embedding else 0.0
            score = (lexical * 3.0) + (importance * 2.0) + recency + (vec_sim * 4.0)
            scored.append((score, rid))

        scored.sort(key=lambda x: x[0], reverse=True)
        top = [rid for _, rid in scored[: int(limit)]]

        out: List[Dict[str, Any]] = []
        for rid in top:
            r = by_rowid.get(rid)
            if not r:
                continue
            try:
                tags = json.loads(r["tags_json"] or "[]")
            except Exception:
                tags = []
            out.append(
                {
                    "id": str(r["fingerprint"]),
                    "type": str(r["type"]),
                    "content": str(r["content"]),
                    "context": str(r["context"]),
                    "importance": int(r["importance"] or 0),
                    "tags": list(tags or []),
                    "last_seen_ms": int(r["last_seen_ms"] or 0),
                    "count": int(r["count"] or 0),
                }
            )
        return out
