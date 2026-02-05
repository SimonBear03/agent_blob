"""
LLM-based memory extraction from conversations.
"""

import os
import time
import json
from typing import List, Optional
from datetime import datetime
from openai import AsyncOpenAI

from .models import Memory, MemoryType, MemoryExtractionResult


class MemoryExtractor:
    """
    Extract important information from conversation turns using LLM.
    """
    
    def __init__(self, openai_client: Optional[AsyncOpenAI] = None):
        self.client = openai_client or AsyncOpenAI(api_key=os.getenv("OPENAI_API_KEY"))
        self.model = os.getenv("MEMORY_EXTRACTION_MODEL", "gpt-4o-mini")
        self.min_importance = 6  # Only extract memories with importance >= 6
    
    async def extract_from_turn(
        self,
        user_msg: str,
        assistant_msg: str,
        session_id: str,
        user_message_id: str,
        assistant_message_id: str
    ) -> MemoryExtractionResult:
        """
        Extract memories from a conversation turn.
        
        Args:
            user_msg: User's message
            assistant_msg: Assistant's response
            session_id: Session this turn belongs to
            user_message_id: ID of user message
            assistant_message_id: ID of assistant message
        
        Returns:
            MemoryExtractionResult with extracted memories
        """
        start_time = time.time()
        
        extraction_prompt = self._build_extraction_prompt(user_msg, assistant_msg)
        
        try:
            response = await self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {
                        "role": "system",
                        "content": self._get_system_prompt()
                    },
                    {
                        "role": "user",
                        "content": extraction_prompt
                    }
                ],
                temperature=0.3,
                response_format={"type": "json_object"}
            )
            
            content = response.choices[0].message.content
            tokens_used = response.usage.total_tokens
            
            # Parse the JSON response
            extraction_data = json.loads(content)
            memories_data = extraction_data.get("memories", [])
            
            # Convert to Memory objects
            memories = []
            timestamp = datetime.utcnow().isoformat() + "Z"
            
            for i, mem_data in enumerate(memories_data):
                # Filter by importance
                importance = mem_data.get("importance", 5)
                if importance < self.min_importance:
                    continue
                
                memory = Memory(
                    id=f"mem_{session_id}_{int(time.time())}_{i}",
                    timestamp=timestamp,
                    session_id=session_id,
                    type=MemoryType(mem_data.get("type", "fact")),
                    content=mem_data["content"],
                    context=mem_data.get("context", ""),
                    importance=importance,
                    tags=mem_data.get("tags", []),
                    source_messages=[user_message_id, assistant_message_id],
                    embedding=None,  # Generated later by storage layer
                    supersedes=mem_data.get("supersedes")
                )
                memories.append(memory)
            
            extraction_time = time.time() - start_time
            
            return MemoryExtractionResult(
                memories=memories,
                extraction_time=extraction_time,
                tokens_used=tokens_used
            )
        
        except Exception as e:
            print(f"Error extracting memories: {e}")
            return MemoryExtractionResult(
                memories=[],
                extraction_time=time.time() - start_time,
                tokens_used=0
            )
    
    def _get_system_prompt(self) -> str:
        """Get system prompt for memory extraction"""
        return """You are a memory extraction system. Your job is to identify and extract important information from conversations that should be remembered long-term.

Extract the following types of information:
- **Facts**: New information learned about the user, their projects, or the world
- **Preferences**: User's likes, dislikes, working style, preferences
- **Decisions**: Choices made, approaches selected, directions taken
- **Questions**: Open questions or topics to follow up on
- **Project**: Project-specific context, goals, requirements

For each memory extracted:
1. Determine the type (fact, preference, decision, question, or project)
2. Write clear, self-contained content (should make sense without context)
3. Add context about when/why this matters
4. Rate importance (1-10, where 10 is critical, 1 is trivial)
5. Add relevant tags for organization
6. If this updates/replaces previous info, note what it supersedes

Only extract truly important information - not casual chat or temporary details.

Return a JSON object with this structure:
{
  "memories": [
    {
      "type": "preference|fact|decision|question|project",
      "content": "Clear, self-contained statement",
      "context": "Why this matters or when relevant",
      "importance": 8,
      "tags": ["tag1", "tag2"],
      "supersedes": "optional_memory_id"
    }
  ]
}"""
    
    def _build_extraction_prompt(self, user_msg: str, assistant_msg: str) -> str:
        """Build the extraction prompt"""
        return f"""Extract important information from this conversation turn:

**User:** {user_msg}

**Assistant:** {assistant_msg}

Analyze this exchange and extract memories worth remembering long-term. Focus on information that provides lasting value - facts, preferences, decisions, or important context.

Return the extraction as JSON."""
    
    async def should_extract(self, user_msg: str, assistant_msg: str) -> bool:
        """
        Quick heuristic to decide if extraction is worth trying.
        Saves API calls for trivial exchanges.
        """
        # Don't extract from very short exchanges
        if len(user_msg) < 10 or len(assistant_msg) < 20:
            return False
        
        # Don't extract from greetings/acknowledgments
        trivial_patterns = ["hello", "hi", "thanks", "ok", "yes", "no", "sure"]
        if user_msg.lower().strip() in trivial_patterns:
            return False
        
        return True
