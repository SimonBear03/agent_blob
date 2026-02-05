"""
LLM-based conversation summarization for compaction.
"""

import os
from typing import List, Dict, Any
from openai import AsyncOpenAI

from ..storage.models import MessageTurn, RollingSummary


class ConversationSummarizer:
    """Generate structured summaries of conversation history"""
    
    def __init__(self, openai_client: AsyncOpenAI):
        self.client = openai_client
        self.model = os.getenv("SUMMARIZATION_MODEL", "gpt-4o-mini")
    
    async def generate_summary(
        self,
        turns: List[MessageTurn],
        previous_summary: RollingSummary
    ) -> RollingSummary:
        """
        Generate structured summary of conversation turns.
        
        Args:
            turns: Conversation turns to summarize
            previous_summary: Previous rolling summary to build upon
        
        Returns:
            Updated RollingSummary
        """
        # Build conversation text
        conversation_text = []
        for turn in turns:
            conversation_text.append(f"User: {turn.user_message}")
            conversation_text.append(f"Assistant: {turn.assistant_message}")
        
        # Build prompt
        prompt = self._build_summary_prompt(
            conversation_text="\n\n".join(conversation_text),
            previous_summary=previous_summary
        )
        
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
                        "content": prompt
                    }
                ],
                temperature=0.3,
                response_format={"type": "json_object"}
            )
            
            import json
            summary_data = json.loads(response.choices[0].message.content)
            
            # Parse into RollingSummary
            return RollingSummary(
                user_profile=summary_data.get("user_profile", ""),
                active_topics=summary_data.get("active_topics", []),
                decisions=summary_data.get("decisions", []),
                open_questions=summary_data.get("open_questions", []),
                tool_context=summary_data.get("tool_context", "")
            )
        
        except Exception as e:
            print(f"Error generating summary: {e}")
            # Return previous summary as fallback
            return previous_summary
    
    def _get_system_prompt(self) -> str:
        """Get system prompt for summarization"""
        return """You are a conversation summarization system. Generate structured, mergeable summaries of conversations.

Your summaries should be:
1. **Stable**: Use consistent format and categories
2. **Cumulative**: Build on previous summaries, don't just summarize new turns
3. **Actionable**: Focus on information that will be useful in future conversations
4. **Concise**: Each bullet should be clear and self-contained

Format:
- **User profile**: Key facts about the user (name, timezone, preferences, working style)
- **Active topics**: Current discussion themes (3-5 items)
- **Decisions**: Important choices made (what, when, why)
- **Open questions**: Topics to follow up on or unresolved issues
- **Tool context**: Important context about tools, files, directories being worked with

Return a JSON object with this structure:
{
  "user_profile": "Simon; timezone Asia/Shanghai; prefers JSONL for transparency",
  "active_topics": ["Memory architecture", "Hybrid search", "JSONL storage"],
  "decisions": [
    "Use JSONL for events (transparent, debuggable)",
    "Hybrid search with BM25 + vector",
    "Reranking layer for precision"
  ],
  "open_questions": ["Which embedding model to use?"],
  "tool_context": "Working in /Users/simon/Documents/GitHub/agent_blob"
}"""
    
    def _build_summary_prompt(
        self,
        conversation_text: str,
        previous_summary: RollingSummary
    ) -> str:
        """Build the summarization prompt"""
        previous_text = ""
        if previous_summary.user_profile or previous_summary.active_topics:
            previous_text = f"""
## Previous Summary
{previous_summary.to_text()}

## Instructions
Update the summary by integrating new information from the conversation below.
- Keep important info from previous summary
- Add new facts, topics, decisions from new conversation
- Remove outdated or resolved items
- Keep it concise and well-organized
"""
        else:
            previous_text = """
## Instructions
Create an initial summary of this conversation.
Focus on lasting information worth remembering.
"""
        
        return f"""{previous_text}

## Conversation to Summarize
{conversation_text}

Generate the updated structured summary as JSON."""
    
    async def merge_summaries(
        self,
        summary1: RollingSummary,
        summary2: RollingSummary
    ) -> RollingSummary:
        """
        Merge two summaries into one.
        Useful when combining summaries from different sources.
        """
        # Simple merge strategy: combine and deduplicate
        merged = RollingSummary(
            user_profile=summary2.user_profile or summary1.user_profile,
            active_topics=list(set(summary1.active_topics + summary2.active_topics)),
            decisions=list(set(summary1.decisions + summary2.decisions)),
            open_questions=list(set(summary1.open_questions + summary2.open_questions)),
            tool_context=summary2.tool_context or summary1.tool_context
        )
        
        # Limit lengths
        merged.active_topics = merged.active_topics[:5]
        merged.decisions = merged.decisions[:10]
        merged.open_questions = merged.open_questions[:5]
        
        return merged
