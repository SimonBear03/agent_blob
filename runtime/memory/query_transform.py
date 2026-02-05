"""
Query transformation techniques for improved retrieval:
- HyDE: Hypothetical Document Embeddings
- Multi-query: Generate query variations
- Decomposition: Break complex queries into sub-queries
"""

import os
from typing import List
from openai import AsyncOpenAI


class QueryTransformer:
    """Transform queries to improve retrieval"""
    
    def __init__(self, openai_client: AsyncOpenAI):
        self.client = openai_client
        self.model = os.getenv("QUERY_TRANSFORM_MODEL", "gpt-4o-mini")
    
    async def transform(
        self,
        query: str,
        methods: List[str] = ["multi_query"]
    ) -> List[str]:
        """
        Transform a query using specified methods.
        
        Args:
            query: Original query
            methods: List of transformation methods to apply
                Options: "hyde", "multi_query", "decompose"
        
        Returns:
            List of transformed queries (includes original)
        """
        queries = [query]  # Always include original
        
        if "hyde" in methods:
            hyde_query = await self.hyde(query)
            if hyde_query:
                queries.append(hyde_query)
        
        if "multi_query" in methods:
            variations = await self.multi_query(query)
            queries.extend(variations)
        
        if "decompose" in methods:
            sub_queries = await self.decompose(query)
            queries.extend(sub_queries)
        
        # Deduplicate while preserving order
        seen = set()
        unique_queries = []
        for q in queries:
            if q.lower() not in seen:
                seen.add(q.lower())
                unique_queries.append(q)
        
        return unique_queries
    
    async def hyde(self, query: str) -> str:
        """
        HyDE: Generate a hypothetical document that would answer the query.
        This often improves semantic matching.
        """
        prompt = f"""Given this query: "{query}"

Generate a hypothetical answer or document snippet that would contain the information being sought. Write as if you're the memory/document that answers this query.

Be concise (1-2 sentences) and focus on the likely content, not explaining what would be in it.

Example:
Query: "What did I decide about storage?"
HyDE: "User decided to use JSONL for event storage because it's transparent and debuggable"

Your turn:"""
        
        try:
            response = await self.client.chat.completions.create(
                model=self.model,
                messages=[{"role": "user", "content": prompt}],
                temperature=0.3,
                max_tokens=100
            )
            return response.choices[0].message.content.strip()
        except Exception as e:
            print(f"Error in HyDE: {e}")
            return ""
    
    async def multi_query(self, query: str, num_variations: int = 2) -> List[str]:
        """
        Generate multiple variations of the query.
        Helps catch different phrasings.
        """
        prompt = f"""Given this query: "{query}"

Generate {num_variations} alternative ways to phrase this query that preserve the same intent but use different words or perspectives.

Return ONLY the alternative queries, one per line, nothing else.

Example:
Query: "What did I decide about storage?"
Alternatives:
storage decision
architecture choice for data persistence

Your turn:"""
        
        try:
            response = await self.client.chat.completions.create(
                model=self.model,
                messages=[{"role": "user", "content": prompt}],
                temperature=0.5,
                max_tokens=100
            )
            
            content = response.choices[0].message.content.strip()
            variations = [line.strip() for line in content.split('\n') if line.strip()]
            return variations[:num_variations]
        
        except Exception as e:
            print(f"Error in multi-query: {e}")
            return []
    
    async def decompose(self, query: str) -> List[str]:
        """
        Decompose complex queries into simpler sub-queries.
        """
        # Simple heuristic: only decompose if query is long or has multiple parts
        if len(query.split()) < 8:
            return []  # Too simple to decompose
        
        prompt = f"""Given this query: "{query}"

If this query contains multiple distinct questions or aspects, break it into simpler sub-queries. If it's already simple, return an empty list.

Return ONLY the sub-queries, one per line, nothing else. If no decomposition needed, return "NONE".

Example:
Query: "What did I decide about storage and how does it relate to the memory system?"
Sub-queries:
storage decision
memory system architecture
relationship between storage and memory

Your turn:"""
        
        try:
            response = await self.client.chat.completions.create(
                model=self.model,
                messages=[{"role": "user", "content": prompt}],
                temperature=0.3,
                max_tokens=150
            )
            
            content = response.choices[0].message.content.strip()
            
            if content.upper() == "NONE":
                return []
            
            sub_queries = [line.strip() for line in content.split('\n') if line.strip()]
            return sub_queries
        
        except Exception as e:
            print(f"Error in decompose: {e}")
            return []
