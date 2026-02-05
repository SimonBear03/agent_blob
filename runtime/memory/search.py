"""
Hybrid memory search combining BM25, vector search, and query transformation.
"""

import asyncio
from typing import List, Dict, Any, Optional
from collections import defaultdict
from openai import AsyncOpenAI

from .storage import MemoryStorage
from .query_transform import QueryTransformer
from .models import Memory


class MemorySearch:
    """
    Hybrid search: BM25 (keyword) + Vector (semantic) + Query Transformation
    """
    
    def __init__(
        self,
        storage: MemoryStorage,
        openai_client: AsyncOpenAI
    ):
        self.storage = storage
        self.query_transformer = QueryTransformer(openai_client)
        self.client = openai_client
    
    async def search(
        self,
        query: str,
        top_k: int = 5,
        use_query_transform: bool = True,
        keyword_weight: float = 0.4,
        vector_weight: float = 0.6
    ) -> List[Memory]:
        """
        Perform hybrid search with query transformation.
        
        Args:
            query: Search query
            top_k: Number of results to return
            use_query_transform: Whether to use query transformation
            keyword_weight: Weight for BM25 scores (0-1)
            vector_weight: Weight for vector scores (0-1)
        
        Returns:
            List of Memory objects, ranked by hybrid score
        """
        # 1. Query transformation
        queries = [query]
        if use_query_transform:
            queries = await self.query_transformer.transform(
                query,
                methods=["multi_query"]  # Start with just multi-query
            )
        
        # 2. Search with all queries
        all_keyword_results = []
        all_vector_results = []
        
        for q in queries:
            # Keyword search
            keyword_results = await self.storage.search_keywords(q, limit=top_k * 3)
            all_keyword_results.extend(keyword_results)
            
            # Vector search (need embedding)
            query_embedding = await self.storage.generate_embedding(q)
            vector_results = await self.storage.search_vectors(query_embedding, limit=top_k * 3)
            all_vector_results.extend(vector_results)
        
        # 3. Merge results with hybrid scoring
        candidates = self._merge_results(
            all_keyword_results,
            all_vector_results,
            keyword_weight,
            vector_weight
        )
        
        # 4. Get top candidates
        top_candidates = candidates[:top_k * 2]  # Get 2x for reranking
        
        # 5. Load full memory objects
        memory_ids = [c["memory_id"] for c in top_candidates]
        memories = await self.storage.load_memories_by_ids(memory_ids)
        
        # 6. Sort by hybrid score
        id_to_score = {c["memory_id"]: c["score"] for c in top_candidates}
        memories.sort(key=lambda m: id_to_score.get(m.id, 0), reverse=True)
        
        return memories[:top_k]
    
    def _merge_results(
        self,
        keyword_results: List[Dict[str, Any]],
        vector_results: List[Dict[str, Any]],
        keyword_weight: float,
        vector_weight: float
    ) -> List[Dict[str, Any]]:
        """
        Merge and rank results from both search methods.
        Uses weighted score combination.
        """
        # Aggregate scores by memory_id
        scores = defaultdict(lambda: {"keyword": 0.0, "vector": 0.0, "count": 0})
        
        # Normalize keyword scores (BM25 ranks)
        if keyword_results:
            max_keyword = max(r["score"] for r in keyword_results)
            for result in keyword_results:
                memory_id = result["memory_id"]
                normalized_score = result["score"] / max_keyword if max_keyword > 0 else 0
                scores[memory_id]["keyword"] = max(scores[memory_id]["keyword"], normalized_score)
                scores[memory_id]["count"] += 1
        
        # Normalize vector scores (cosine similarity, already 0-1)
        for result in vector_results:
            memory_id = result["memory_id"]
            scores[memory_id]["vector"] = max(scores[memory_id]["vector"], result["score"])
            scores[memory_id]["count"] += 1
        
        # Compute hybrid scores
        ranked = []
        for memory_id, score_data in scores.items():
            hybrid_score = (
                keyword_weight * score_data["keyword"] +
                vector_weight * score_data["vector"]
            )
            ranked.append({
                "memory_id": memory_id,
                "score": hybrid_score,
                "keyword_score": score_data["keyword"],
                "vector_score": score_data["vector"]
            })
        
        # Sort by hybrid score
        ranked.sort(key=lambda x: x["score"], reverse=True)
        
        return ranked
    
    async def search_by_type(
        self,
        query: str,
        memory_type: str,
        top_k: int = 5
    ) -> List[Memory]:
        """
        Search for memories of a specific type.
        """
        # Get more results, then filter by type
        memories = await self.search(query, top_k=top_k * 3, use_query_transform=False)
        
        # Filter by type
        filtered = [m for m in memories if m.type.value == memory_type]
        
        return filtered[:top_k]
    
    async def search_by_tags(
        self,
        tags: List[str],
        top_k: int = 10
    ) -> List[Memory]:
        """
        Search for memories by tags.
        """
        # Build query from tags
        query = " ".join(tags)
        
        return await self.search(query, top_k=top_k, use_query_transform=False)
