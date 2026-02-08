from __future__ import annotations

from typing import Any, Dict, List

from agent_blob import config


class MemoryExtractor:
    """
    Structured long-term memory extraction for a single completed turn.
    The extractor is intentionally strict to reduce low-value memory churn.
    """

    def __init__(self):
        self.model = config.memory_extraction_model() or config.llm_model_name()
        self.min_importance = config.memory_importance_min()

    def _system_prompt(self) -> str:
        return (
            "You extract durable long-term memory for a personal AI assistant.\n"
            "Only extract items that will still matter later.\n"
            "Prefer: facts, preferences, decisions, project constraints, commitments, recurring routines.\n"
            "Avoid: greetings, temporary chatter, and one-off execution noise.\n"
            "Return JSON only with this schema:\n"
            '{ "memories": [ { "type": "fact|preference|decision|project|routine|constraint",'
            ' "content": "string", "context": "string", "importance": 1, "tags": ["string"] } ] }\n'
            "importance must be 1-10."
        )

    def _user_prompt(self, user_text: str, assistant_text: str) -> str:
        return (
            "Extract durable memories from this exchange.\n\n"
            f"USER:\n{user_text}\n\n"
            f"ASSISTANT:\n{assistant_text}\n"
        )

    async def extract(self, *, llm: Any, user_text: str, assistant_text: str) -> List[Dict[str, Any]]:
        if len((user_text or "").strip()) < 8:
            return []
        if len((assistant_text or "").strip()) < 8:
            return []

        data = await llm.chat_json(
            model=self.model,
            messages=[
                {"role": "system", "content": self._system_prompt()},
                {"role": "user", "content": self._user_prompt(user_text, assistant_text)},
            ],
        )
        raw = data.get("memories") if isinstance(data, dict) else None
        if not isinstance(raw, list):
            return []

        out: List[Dict[str, Any]] = []
        for item in raw:
            if not isinstance(item, dict):
                continue
            mem_type = str(item.get("type", "") or "").strip()
            content = str(item.get("content", "") or "").strip()
            if not mem_type or not content:
                continue
            try:
                importance = int(item.get("importance", 0) or 0)
            except Exception:
                importance = 0
            if importance < self.min_importance:
                continue
            out.append(
                {
                    "type": mem_type,
                    "content": content,
                    "context": str(item.get("context", "") or "").strip(),
                    "importance": importance,
                    "tags": [str(x) for x in (item.get("tags") or []) if str(x).strip()],
                }
            )
        return out
