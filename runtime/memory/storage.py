"""
Memory storage with JSONL files and dual indexing (keyword + vector).
"""

import os
import json
import aiofiles
import aiosqlite
import numpy as np
from pathlib import Path
from typing import List, Optional, Dict, Any
from datetime import datetime, date
from openai import AsyncOpenAI

from .models import Memory


class MemoryStorage:
    """
    Store memories in JSONL files with dual indexing:
    - SQLite FTS5 for keyword search
    - NumPy arrays for vector search
    """
    
    def __init__(
        self,
        workspace_dir: str = "./data/workspace",
        openai_client: Optional[AsyncOpenAI] = None
    ):
        self.workspace_dir = Path(workspace_dir)
        self.facts_dir = self.workspace_dir / "memory" / "facts"
        self.index_dir = self.workspace_dir / "memory" / "index"
        self.vectors_dir = self.index_dir / "vectors"
        
        # Create directories
        self.facts_dir.mkdir(parents=True, exist_ok=True)
        self.index_dir.mkdir(parents=True, exist_ok=True)
        self.vectors_dir.mkdir(parents=True, exist_ok=True)
        
        self.fts_db_path = self.index_dir / "facts.db"
        self.vectors_file = self.vectors_dir / "facts.npy"
        self.metadata_file = self.vectors_dir / "metadata.json"
        
        self.client = openai_client or AsyncOpenAI(api_key=os.getenv("OPENAI_API_KEY"))
        self.embedding_model = "text-embedding-3-small"
        self.embedding_dim = 1536
        
        # In-memory cache for vectors (loaded on first use)
        self._vectors: Optional[np.ndarray] = None
        self._metadata: Optional[Dict[str, Any]] = None
    
    async def initialize(self):
        """Initialize storage (create FTS table, load vectors)"""
        await self._init_fts_db()
        await self._load_vectors()
    
    async def _init_fts_db(self):
        """Initialize SQLite FTS5 database"""
        async with aiosqlite.connect(self.fts_db_path) as db:
            await db.execute("""
                CREATE VIRTUAL TABLE IF NOT EXISTS facts_fts USING fts5(
                    memory_id UNINDEXED,
                    content,
                    context,
                    tags
                )
            """)
            await db.commit()
    
    async def _load_vectors(self):
        """Load vector index into memory"""
        if self.vectors_file.exists():
            self._vectors = np.load(str(self.vectors_file))
        else:
            self._vectors = np.zeros((0, self.embedding_dim))
        
        if self.metadata_file.exists():
            with open(self.metadata_file, 'r') as f:
                self._metadata = json.load(f)
        else:
            self._metadata = {"memory_ids": [], "count": 0}
    
    async def save_memory(self, memory: Memory) -> None:
        """
        Save memory to:
        1. Daily JSONL file
        2. SQLite FTS index
        3. Vector index (after generating embedding)
        """
        # 1. Append to daily JSONL
        today = date.today().isoformat()
        facts_file = self.facts_dir / f"{today}.jsonl"
        
        async with aiofiles.open(facts_file, "a", encoding="utf-8") as f:
            await f.write(memory.to_json_line() + "\n")
        
        # 2. Generate embedding if not present
        if memory.embedding is None:
            memory.embedding = await self.generate_embedding(memory.to_search_text())
        
        # 3. Index keywords in FTS
        await self.index_keywords(memory)
        
        # 4. Store vector
        await self.store_vector(memory.id, memory.embedding)
    
    async def index_keywords(self, memory: Memory) -> None:
        """Index memory in SQLite FTS for keyword search"""
        async with aiosqlite.connect(self.fts_db_path) as db:
            await db.execute(
                """
                INSERT INTO facts_fts (memory_id, content, context, tags)
                VALUES (?, ?, ?, ?)
                """,
                (
                    memory.id,
                    memory.content,
                    memory.context,
                    " ".join(memory.tags)
                )
            )
            await db.commit()
    
    async def generate_embedding(self, text: str) -> List[float]:
        """Generate embedding using OpenAI API"""
        try:
            response = await self.client.embeddings.create(
                model=self.embedding_model,
                input=text
            )
            return response.data[0].embedding
        except Exception as e:
            print(f"Error generating embedding: {e}")
            # Return zero vector as fallback
            return [0.0] * self.embedding_dim
    
    async def store_vector(self, memory_id: str, embedding: List[float]) -> None:
        """Add vector to the index"""
        # Ensure vectors are loaded
        if self._vectors is None:
            await self._load_vectors()
        
        # Convert to numpy array
        vector = np.array(embedding, dtype=np.float32).reshape(1, -1)
        
        # Append to vectors array
        self._vectors = np.vstack([self._vectors, vector])
        
        # Update metadata
        self._metadata["memory_ids"].append(memory_id)
        self._metadata["count"] += 1
        
        # Save to disk
        np.save(str(self.vectors_file), self._vectors)
        with open(self.metadata_file, 'w') as f:
            json.dump(self._metadata, f)
    
    async def search_keywords(
        self,
        query: str,
        limit: int = 20
    ) -> List[Dict[str, Any]]:
        """
        Search memories using SQLite FTS (BM25).
        
        Returns list of {"memory_id": str, "score": float}
        """
        # Sanitize query for FTS5 - escape special characters
        # FTS5 special chars: " ( ) < > - : * AND OR NOT NEAR
        sanitized = query.replace('"', '""')  # Escape quotes
        # Remove other special FTS5 operators that could cause syntax errors
        for char in ['<', '>', '(', ')', ':', '*']:
            sanitized = sanitized.replace(char, ' ')
        
        # Wrap in quotes to treat as literal phrase
        fts_query = f'"{sanitized}"'
        
        async with aiosqlite.connect(self.fts_db_path) as db:
            try:
                cursor = await db.execute(
                    """
                    SELECT memory_id, rank
                    FROM facts_fts
                    WHERE facts_fts MATCH ?
                    ORDER BY rank
                    LIMIT ?
                    """,
                    (fts_query, limit)
                )
                results = await cursor.fetchall()
                
                return [
                    {"memory_id": row[0], "score": -row[1]}  # Negative rank = higher is better
                    for row in results
                ]
            except Exception as e:
                # If FTS query still fails, return empty results
                print(f"FTS search error (returning empty): {e}")
                return []
    
    async def search_vectors(
        self,
        query_embedding: List[float],
        limit: int = 20
    ) -> List[Dict[str, Any]]:
        """
        Search memories using vector similarity (cosine).
        
        Returns list of {"memory_id": str, "score": float}
        """
        # Ensure vectors are loaded
        if self._vectors is None or self._metadata is None:
            await self._load_vectors()
        
        if len(self._metadata["memory_ids"]) == 0:
            return []
        
        # Convert query to numpy
        query_vec = np.array(query_embedding, dtype=np.float32).reshape(1, -1)
        
        # Normalize vectors
        query_norm = query_vec / (np.linalg.norm(query_vec) + 1e-10)
        vectors_norm = self._vectors / (np.linalg.norm(self._vectors, axis=1, keepdims=True) + 1e-10)
        
        # Compute cosine similarity
        similarities = np.dot(vectors_norm, query_norm.T).flatten()
        
        # Get top K indices
        top_indices = np.argsort(similarities)[-limit:][::-1]
        
        results = []
        for idx in top_indices:
            if idx < len(self._metadata["memory_ids"]):
                results.append({
                    "memory_id": self._metadata["memory_ids"][idx],
                    "score": float(similarities[idx])
                })
        
        return results
    
    async def load_memory_by_id(self, memory_id: str) -> Optional[Memory]:
        """
        Load a memory by ID.
        This requires scanning JSONL files (slow - use sparingly).
        """
        # Scan all JSONL files in facts directory
        for facts_file in self.facts_dir.glob("*.jsonl"):
            async with aiofiles.open(facts_file, "r", encoding="utf-8") as f:
                async for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        memory = Memory.from_json_line(line)
                        if memory.id == memory_id:
                            return memory
                    except:
                        continue
        
        return None
    
    async def load_memories_by_ids(self, memory_ids: List[str]) -> List[Memory]:
        """Load multiple memories by IDs"""
        memories = []
        for memory_id in memory_ids:
            memory = await self.load_memory_by_id(memory_id)
            if memory:
                memories.append(memory)
        return memories
