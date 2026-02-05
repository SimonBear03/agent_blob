"""
Reranking layer for improved precision using cross-encoder models.
"""

import os
from typing import List, Dict, Any, Optional
from openai import AsyncOpenAI

from .models import Memory


class MemoryReranker:
    """
    Rerank search results using cross-encoder or LLM-based reranking.
    
    Professional systems use dedicated cross-encoder models like:
    - mixedbread-ai/mxbai-rerank-base-v1
    - BAAI/bge-reranker-large
    - Cohere rerank API
    
    For simplicity, we implement LLM-based reranking which is more
    accessible and doesn't require additional model hosting.
    """
    
    def __init__(self, openai_client: AsyncOpenAI):
        self.client = openai_client
        self.model = os.getenv("RERANK_MODEL", "gpt-4o-mini")
    
    async def rerank(
        self,
        query: str,
        memories: List[Memory],
        top_k: Optional[int] = None
    ) -> List[Memory]:
        """
        Rerank memories for relevance to query.
        
        Args:
            query: Original query
            memories: List of candidate memories
            top_k: Return top K (default: return all, reranked)
        
        Returns:
            Reranked list of memories
        """
        if len(memories) == 0:
            return []
        
        if len(memories) == 1:
            return memories
        
        # For small sets, use LLM-based reranking
        if len(memories) <= 10:
            reranked = await self._llm_rerank(query, memories)
        else:
            # For larger sets, use heuristic reranking (faster)
            reranked = self._heuristic_rerank(query, memories)
        
        if top_k:
            return reranked[:top_k]
        return reranked
    
    async def _llm_rerank(
        self,
        query: str,
        memories: List[Memory]
    ) -> List[Memory]:
        """
        Use LLM to rerank based on relevance.
        More accurate but slower than heuristics.
        """
        # Build prompt with numbered memories
        memories_text = []
        for i, mem in enumerate(memories, 1):
            memories_text.append(
                f"{i}. [{mem.type.value}] {mem.content}\n"
                f"   Context: {mem.context}\n"
                f"   Tags: {', '.join(mem.tags)}"
            )
        
        prompt = f"""Given this query: "{query}"

Rank these memories by relevance to the query. Consider:
- Direct relevance to the query topic
- Importance and specificity
- Recency (if applicable)

Memories:
{chr(10).join(memories_text)}

Return ONLY the numbers of the memories in order from most to least relevant, comma-separated.
Example: 3,1,5,2,4

Your ranking:"""
        
        try:
            response = await self.client.chat.completions.create(
                model=self.model,
                messages=[{"role": "user", "content": prompt}],
                temperature=0.1,
                max_tokens=100
            )
            
            ranking_text = response.choices[0].message.content.strip()
            
            # Parse ranking
            try:
                rankings = [int(x.strip()) - 1 for x in ranking_text.split(',')]
                # Validate rankings
                valid_rankings = [r for r in rankings if 0 <= r < len(memories)]
                
                # Reorder memories
                reranked = [memories[i] for i in valid_rankings]
                
                # Add any memories that weren't ranked
                ranked_set = set(valid_rankings)
                for i, mem in enumerate(memories):
                    if i not in ranked_set:
                        reranked.append(mem)
                
                return reranked
            
            except (ValueError, IndexError) as e:
                print(f"Error parsing reranking: {e}")
                return memories  # Return original order
        
        except Exception as e:
            print(f"Error in LLM reranking: {e}")
            return memories
    
    def _heuristic_rerank(
        self,
        query: str,
        memories: List[Memory]
    ) -> List[Memory]:
        """
        Fast heuristic reranking based on:
        - Importance score
        - Content length (longer = more detailed)
        - Tag overlap with query
        """
        query_terms = set(query.lower().split())
        
        scored_memories = []
        for mem in memories:
            # Base score from importance
            score = mem.importance / 10.0
            
            # Boost for content length (up to 50 chars = +0.2)
            length_boost = min(len(mem.content) / 250.0, 0.2)
            score += length_boost
            
            # Boost for tag overlap
            mem_tags = set(tag.lower() for tag in mem.tags)
            overlap = len(query_terms & mem_tags)
            score += overlap * 0.1
            
            scored_memories.append((score, mem))
        
        # Sort by score
        scored_memories.sort(key=lambda x: x[0], reverse=True)
        
        return [mem for _, mem in scored_memories]
