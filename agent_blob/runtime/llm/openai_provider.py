from __future__ import annotations

import os
from typing import Any, AsyncIterator, Dict, List, Optional


class OpenAIChatCompletionsProvider:
    """
    Streaming chat provider using OpenAI's Chat Completions API.

    Keeps a minimal surface area so we can swap to another provider (local models, etc.)
    without changing the runtime.
    """

    def __init__(self, api_key: Optional[str] = None):
        self.api_key = api_key or os.getenv("OPENAI_API_KEY", "")

        if not self.api_key:
            raise RuntimeError("OPENAI_API_KEY is not set")

        # Import lazily so non-LLM paths (tests, tools-only) don't require openai installed.
        from openai import AsyncOpenAI  # type: ignore

        self._client = AsyncOpenAI(api_key=self.api_key)

    async def stream_chat(self, *, model: str, messages: List[Dict[str, Any]]) -> AsyncIterator[str]:
        stream = await self._client.chat.completions.create(
            model=model,
            messages=messages,
            stream=True,
            temperature=0.7,
        )
        async for chunk in stream:
            if not getattr(chunk, "choices", None):
                continue
            delta = chunk.choices[0].delta
            content = getattr(delta, "content", None)
            if content:
                yield content

