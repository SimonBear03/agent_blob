from __future__ import annotations

from typing import Any, AsyncIterator, Dict, List, Protocol


class LLMProvider(Protocol):
    async def stream_chat(self, *, model: str, messages: List[Dict[str, Any]]) -> AsyncIterator[str]:
        ...

