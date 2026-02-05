from __future__ import annotations

import json
import os
from typing import Any, Dict, List, Optional

from agent_blob import config


class MemoryExtractor:
    """
    LLM-based extraction of structured long-term memories from a turn.

    Output shape:
      {"memories":[{"type":..., "content":..., "context":..., "importance":1-10, "tags":[...]}]}
    """

    def __init__(self):
        self.model = config.memory_extraction_model() or config.llm_model_name()
        self.min_importance = config.memory_importance_min()

    def _system_prompt(self) -> str:
        return (
            "You are a memory extraction system for a personal AI.\n"
            "Extract only durable long-term memories that will be useful later.\n"
            "Prefer concrete facts, preferences, decisions, ongoing projects, and open questions.\n"
            "Avoid transient details, greetings, or one-off execution results unless they matter long-term.\n\n"
            "If the user explicitly asks you to remember something (e.g. 'please remember ...'), you should almost always extract it\n"
            "as a high-importance memory (importance 9-10) with a tag like 'explicit'.\n\n"
            "Return JSON ONLY with this schema:\n"
            '{ "memories": [ { "type": "fact|preference|decision|project|question",'
            ' "content": "string", "context": "string", "importance": 1, "tags": ["string"] } ] }\n'
            "importance is 1-10, where 10 is critical.\n"
        )

    def _user_prompt(self, user_text: str, assistant_text: str) -> str:
        return (
            "Extract durable memories from this exchange.\n\n"
            f"USER:\n{user_text}\n\nASSISTANT:\n{assistant_text}\n"
        )

    async def extract(self, *, llm: Any, user_text: str, assistant_text: str) -> List[Dict[str, Any]]:
        # Quick heuristic: skip trivial turns
        if len((user_text or "").strip()) < 8:
            return []
        if len((assistant_text or "").strip()) < 16:
            return []

        data = await llm.chat_json(
            model=self.model,
            messages=[
                {"role": "system", "content": self._system_prompt()},
                {"role": "user", "content": self._user_prompt(user_text, assistant_text)},
            ],
        )
        memories = data.get("memories") if isinstance(data, dict) else None
        if not isinstance(memories, list):
            return []

        out: List[Dict[str, Any]] = []
        for m in memories:
            if not isinstance(m, dict):
                continue
            importance = int(m.get("importance", 0) or 0)
            if importance < self.min_importance:
                continue
            mem_type = str(m.get("type", "") or "").strip()
            content = str(m.get("content", "") or "").strip()
            if not mem_type or not content:
                continue
            out.append(
                {
                    "type": mem_type,
                    "content": content,
                    "context": str(m.get("context", "") or "").strip(),
                    "importance": importance,
                    "tags": list(m.get("tags") or []),
                }
            )
        return out
