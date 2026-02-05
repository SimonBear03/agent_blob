"""
Session compaction manager for context window management.
"""

import os
from typing import Optional
from datetime import datetime

from ..storage.models import SessionState, RollingSummary, create_compaction_event
from ..storage.session_store import SessionStore
from ..storage.state_cache import StateCache
from .summarizer import ConversationSummarizer
from ..memory.extractor import MemoryExtractor
from ..memory.storage import MemoryStorage
from shared.model_config import get_model_context_limit, get_current_model


class SessionCompactor:
    """
    Manage context window via rolling compaction.
    
    When a session approaches context limit:
    1. Generate structured summary of older turns
    2. Keep last N turns verbatim
    3. Extract key facts to workspace memory
    4. Update state cache
    5. Log compaction event
    """
    
    def __init__(
        self,
        session_store: SessionStore,
        state_cache: StateCache,
        summarizer: ConversationSummarizer,
        memory_extractor: Optional[MemoryExtractor] = None,
        memory_storage: Optional[MemoryStorage] = None
    ):
        self.session_store = session_store
        self.state_cache = state_cache
        self.summarizer = summarizer
        self.memory_extractor = memory_extractor
        self.memory_storage = memory_storage
        
        # Compaction settings
        self.compaction_threshold = 0.6  # Compact at 60% of context window
        self.keep_recent_turns = 30  # Keep last 30 turns verbatim
        self.min_turns_for_compaction = 40  # Only compact if we have enough turns
    
    async def should_compact(
        self,
        state: SessionState,
        model: Optional[str] = None
    ) -> bool:
        """
        Check if compaction is needed.
        
        Args:
            state: Current session state
            model: Model name (to get context limit)
        
        Returns:
            True if compaction should be triggered
        """
        if not model:
            model = get_current_model()
        
        # Get context window limit
        context_limit = get_model_context_limit(model)
        threshold_tokens = int(context_limit * self.compaction_threshold)
        
        # Check if we're above threshold
        if state.token_count >= threshold_tokens:
            # Only compact if we have enough turns
            if state.message_count >= self.min_turns_for_compaction:
                return True
        
        return False
    
    async def compact(
        self,
        session_id: str,
        state: SessionState
    ) -> SessionState:
        """
        Perform compaction on a session.
        
        Args:
            session_id: Session to compact
            state: Current session state
        
        Returns:
            Updated session state after compaction
        """
        print(f"🗜️ Compacting session {session_id} (tokens: {state.token_count}, messages: {state.message_count})")
        
        # 1. Determine how many turns to summarize
        num_turns = len(state.recent_turns)
        if num_turns <= self.keep_recent_turns:
            # Not enough to compact
            return state
        
        turns_to_summarize = state.recent_turns[:-self.keep_recent_turns]
        turns_to_keep = state.recent_turns[-self.keep_recent_turns:]
        
        # 2. Generate structured summary
        new_summary = await self.summarizer.generate_summary(
            turns=turns_to_summarize,
            previous_summary=state.rolling_summary
        )
        
        # 3. Extract key facts to workspace memory (if available)
        facts_extracted = 0
        if self.memory_extractor and self.memory_storage:
            # Extract from turns being compacted
            for turn in turns_to_summarize:
                try:
                    result = await self.memory_extractor.extract_from_turn(
                        user_msg=turn.user_message,
                        assistant_msg=turn.assistant_message,
                        session_id=session_id,
                        user_message_id=turn.user_message_id,
                        assistant_message_id=turn.assistant_message_id
                    )
                    
                    # Save extracted memories
                    for memory in result.memories:
                        await self.memory_storage.save_memory(memory)
                        facts_extracted += 1
                
                except Exception as e:
                    print(f"Error extracting memories during compaction: {e}")
        
        # 4. Update state
        state.rolling_summary = new_summary
        state.recent_turns = turns_to_keep
        state.last_compaction = datetime.utcnow().isoformat() + "Z"
        
        # Estimate new token count (rough approximation)
        # Summary tokens + recent turns tokens
        summary_tokens = len(new_summary.to_text().split()) * 1.3  # Rough token estimate
        recent_turns_tokens = sum(
            len(t.user_message.split()) + len(t.assistant_message.split())
            for t in turns_to_keep
        ) * 1.3
        state.token_count = int(summary_tokens + recent_turns_tokens)
        
        # 5. Save updated state
        await self.state_cache.save_state(state)
        
        # 6. Append compaction event to JSONL
        compaction_event = create_compaction_event(new_summary, facts_extracted)
        await self.session_store.append_event(session_id, compaction_event)
        
        print(f"✅ Compaction complete: {len(turns_to_summarize)} turns summarized, {facts_extracted} facts extracted")
        
        return state
    
    def estimate_tokens(self, text: str) -> int:
        """
        Rough token count estimation.
        Real implementation would use tiktoken or similar.
        """
        # Rough approximation: 1 token ≈ 0.75 words
        words = len(text.split())
        return int(words * 1.3)
