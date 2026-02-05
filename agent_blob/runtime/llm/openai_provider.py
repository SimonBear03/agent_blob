from __future__ import annotations

import os
import json
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

    async def stream_chat_chunks(
        self,
        *,
        model: str,
        messages: List[Dict[str, Any]],
        tools: Optional[List[Dict[str, Any]]] = None,
    ) -> AsyncIterator[Any]:
        """
        Yield raw OpenAI chunks (used for tool-calling accumulation).
        """
        stream = await self._client.chat.completions.create(
            model=model,
            messages=messages,
            tools=tools,
            stream=True,
            temperature=0.7,
        )
        async for chunk in stream:
            yield chunk

    async def chat_json(self, *, model: str, messages: List[Dict[str, Any]]) -> Dict[str, Any]:
        """
        Non-streaming JSON response (used for memory extraction / consolidation).
        """
        resp = await self._client.chat.completions.create(
            model=model,
            messages=messages,
            temperature=0.2,
            response_format={"type": "json_object"},
        )
        content = resp.choices[0].message.content or "{}"
        try:
            return json.loads(content)
        except Exception:
            return {}
