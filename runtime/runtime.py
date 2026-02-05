"""
Agent runtime: memory-aware agent loop with JSONL storage, compaction, and tools.

Replaces the previous v1 runtime. Single entry point for gateway.
"""
import os
import asyncio
import time
from pathlib import Path
from typing import AsyncIterator, Optional, Dict, Any, List
from datetime import datetime
from openai import AsyncOpenAI

from .storage import SessionStore, StateCache, SessionState
from .storage.models import create_message_event, MessageTurn
from .memory import MemoryExtractor, MemoryStorage
from .memory.search import MemorySearch
from .memory.reranker import MemoryReranker
from .compaction import SessionCompactor, ConversationSummarizer
from .tools import ToolRegistry, init_memory_tools


def _to_gateway_event(e: dict, run_id: str) -> dict:
    """Convert internal runtime event to gateway protocol shape."""
    t = e.get("type")
    if t == "status":
        return {
            "type": "event",
            "event": "status",
            "payload": {"runId": run_id, "status": e.get("status", "unknown")},
        }
    if t == "token":
        return {
            "type": "event",
            "event": "token",
            "payload": {"runId": run_id, "content": e.get("content", ""), "delta": True},
        }
    if t == "tool_result":
        return {
            "type": "event",
            "event": "tool_result",
            "payload": {
                "runId": run_id,
                "toolName": e.get("name", ""),
                "result": {"content": e.get("result", "")},
            },
        }
    if t == "final":
        return {
            "type": "event",
            "event": "final",
            "payload": {"runId": run_id, "messageId": "", "totalTokens": 0},
        }
    if t == "error":
        return {
            "type": "event",
            "event": "error",
            "payload": {
                "runId": run_id,
                "message": e.get("error", "Unknown error"),
                "retryable": False,
                "errorCode": None,
            },
        }
    return {
        "type": "event",
        "event": "status",
        "payload": {"runId": run_id, "status": str(t)},
    }


class AgentRuntime:
    """
    Agent runtime with memory, JSONL session storage, compaction, and tools.
    """

    def __init__(self):
        self.openai_client = AsyncOpenAI(api_key=os.getenv("OPENAI_API_KEY"))
        self.model = os.getenv("MODEL_NAME", "gpt-4o")

        self.session_store = SessionStore()
        self.state_cache = StateCache()

        self.memory_storage = MemoryStorage(openai_client=self.openai_client)
        self.memory_extractor = MemoryExtractor(openai_client=self.openai_client)
        self.memory_search = MemorySearch(
            storage=self.memory_storage,
            openai_client=self.openai_client,
        )
        self.memory_reranker = MemoryReranker(openai_client=self.openai_client)

        self.summarizer = ConversationSummarizer(openai_client=self.openai_client)
        self.compactor = SessionCompactor(
            session_store=self.session_store,
            state_cache=self.state_cache,
            summarizer=self.summarizer,
            memory_extractor=self.memory_extractor,
            memory_storage=self.memory_storage,
        )

        self.tool_registry = ToolRegistry()
        self._initialize_tools()

        self.system_prompt = self._load_system_prompt()

    async def initialize(self):
        """Async initialization (e.g. memory storage)."""
        await self.memory_storage.initialize()

    def _initialize_tools(self):
        from .tools import filesystem, session_tools, process_tools, memory_tools

        filesystem.register_tools(self.tool_registry)
        session_tools.register_tools(self.tool_registry)
        process_tools.register_tools(self.tool_registry)
        init_memory_tools(
            self.memory_storage,
            self.memory_search,
            self.memory_reranker,
        )
        memory_tools.register_tools(self.tool_registry)

    def _load_system_prompt(self) -> str:
        root = Path(__file__).resolve().parent.parent
        path = root / "shared" / "prompts" / "system.md"
        try:
            return path.read_text(encoding="utf-8")
        except Exception:
            return "You are a helpful AI assistant with memory and tools."

    def get_model_info(self) -> dict:
        try:
            from shared.model_config import get_model_context_limit
            limit = get_model_context_limit(self.model)
        except Exception:
            limit = 128000
        return {"model_name": self.model, "context_limit": limit}

    async def process(self, request) -> AsyncIterator[Dict[str, Any]]:
        """
        Process an agent request (gateway contract).
        request has session_id, message, run_id.
        Yields gateway-shaped events: {"type":"event","event":"...","payload":{...}}.
        """
        session_id = request.session_id
        message = request.message
        run_id = getattr(request, "run_id", None) or getattr(request, "request_id", "run-0")

        async for e in self._process_impl(session_id, message, run_id):
            yield _to_gateway_event(e, run_id)

    async def _process_impl(
        self,
        session_id: str,
        user_message: str,
        user_message_id: str,
    ) -> AsyncIterator[dict]:
        user_event = create_message_event(
            message_id=user_message_id,
            role="user",
            content=user_message,
        )
        await self.session_store.append_event(session_id, user_event)

        state = await self.state_cache.get_or_create_state(session_id)

        if await self.compactor.should_compact(state, self.model):
            yield {"type": "status", "status": "compacting", "message": "Compacting conversation history..."}
            state = await self.compactor.compact(session_id, state)
            yield {"type": "status", "status": "ready", "message": "Compaction complete"}

        yield {"type": "status", "status": "retrieving_memory", "message": "Searching long-term memory..."}
        relevant_memories = await self.memory_search.search(query=user_message, top_k=5)

        messages = self._build_messages_with_memory(
            state=state,
            user_message=user_message,
            memories=relevant_memories,
        )
        total_chars = sum(len(str(m.get("content", ""))) for m in messages)
        state.token_count = total_chars // 4

        yield {"type": "status", "status": "thinking", "message": "Thinking..."}
        accumulated_response = ""
        tool_calls_dict = {}

        try:
            stream = await self.openai_client.chat.completions.create(
                model=self.model,
                messages=messages,
                tools=self.tool_registry.to_openai_tools(),
                stream=True,
                temperature=0.7,
            )
            yield {"type": "status", "status": "streaming", "message": "Streaming response..."}

            async for chunk in stream:
                if not chunk.choices:
                    continue
                delta = chunk.choices[0].delta
                if delta.content:
                    accumulated_response += delta.content
                    yield {"type": "token", "content": delta.content}
                if delta.tool_calls:
                    for tc_chunk in delta.tool_calls:
                        idx = tc_chunk.index
                        if idx not in tool_calls_dict:
                            tool_calls_dict[idx] = {
                                "id": None,
                                "type": "function",
                                "function": {"name": "", "arguments": ""},
                            }
                        if tc_chunk.id:
                            tool_calls_dict[idx]["id"] = tc_chunk.id
                        if tc_chunk.function:
                            if tc_chunk.function.name:
                                tool_calls_dict[idx]["function"]["name"] += tc_chunk.function.name
                            if tc_chunk.function.arguments:
                                tool_calls_dict[idx]["function"]["arguments"] += tc_chunk.function.arguments or ""

            tool_calls_list = [tool_calls_dict[i] for i in sorted(tool_calls_dict.keys())]

            if tool_calls_list:
                yield {
                    "type": "status",
                    "status": "executing_tools",
                    "message": f"Executing {len(tool_calls_list)} tools...",
                }
                tool_results = []
                for tool_call in tool_calls_list:
                    tool_name = tool_call["function"]["name"]
                    tool_args = tool_call["function"]["arguments"]
                    tool_call_id = tool_call["id"]
                    try:
                        import json
                        args_dict = json.loads(tool_args) if tool_args else {}
                        result = await self.tool_registry.execute_tool(tool_name, args_dict)
                        tool_results.append({
                            "tool_call_id": tool_call_id,
                            "role": "tool",
                            "name": tool_name,
                            "content": str(result),
                        })
                        yield {"type": "tool_result", "name": tool_name, "result": str(result)}
                    except Exception as ex:
                        err = str(ex)
                        tool_results.append({
                            "tool_call_id": tool_call_id,
                            "role": "tool",
                            "name": tool_name,
                            "content": err,
                        })
                        yield {"type": "tool_result", "name": tool_name, "result": err, "error": True}

                messages_with_tools = (
                    messages
                    + [{"role": "assistant", "content": accumulated_response or None, "tool_calls": tool_calls_list}]
                    + tool_results
                )
                yield {"type": "status", "status": "thinking", "message": "Processing tool results..."}
                stream = await self.openai_client.chat.completions.create(
                    model=self.model,
                    messages=messages_with_tools,
                    tools=self.tool_registry.to_openai_tools(),
                    stream=True,
                    temperature=0.7,
                )
                yield {"type": "status", "status": "streaming", "message": "Streaming response..."}
                accumulated_response = ""
                async for chunk in stream:
                    if chunk.choices and chunk.choices[0].delta.content:
                        accumulated_response += chunk.choices[0].delta.content
                        yield {"type": "token", "content": chunk.choices[0].delta.content}

        except Exception as e:
            yield {"type": "error", "error": str(e)}
            return

        assistant_message_id = f"msg_{int(datetime.utcnow().timestamp() * 1000)}"
        assistant_event = create_message_event(
            message_id=assistant_message_id,
            role="assistant",
            content=accumulated_response,
        )
        await self.session_store.append_event(session_id, assistant_event)

        asyncio.create_task(
            self._extract_memories_async(
                session_id=session_id,
                user_message=user_message,
                assistant_message=accumulated_response,
                user_message_id=user_message_id,
                assistant_message_id=assistant_message_id,
            )
        )

        turn = MessageTurn(
            user_message=user_message,
            assistant_message=accumulated_response,
            timestamp=datetime.utcnow().isoformat() + "Z",
            user_message_id=user_message_id,
            assistant_message_id=assistant_message_id,
        )
        state.recent_turns.append(turn)
        state.message_count += 2
        await self.state_cache.save_state(state)

        yield {"type": "final", "message": "Response complete"}

    def _build_messages_with_memory(
        self,
        state: SessionState,
        user_message: str,
        memories: list,
    ) -> list:
        messages = [{"role": "system", "content": self.system_prompt}]
        if state.rolling_summary.user_profile or state.rolling_summary.active_topics:
            messages.append({
                "role": "system",
                "content": f"## Conversation Summary\n{state.rolling_summary.to_text()}",
            })
        if memories:
            mem_text = "## Relevant Long-Term Memories\n\n"
            for mem in memories:
                mem_text += f"- [{mem.type.value}] {mem.content}\n"
                if getattr(mem, "context", None):
                    mem_text += f"  Context: {mem.context}\n"
            messages.append({"role": "system", "content": mem_text})
        for turn in state.recent_turns[-20:]:
            messages.append({"role": "user", "content": turn.user_message})
            messages.append({"role": "assistant", "content": turn.assistant_message})
        messages.append({"role": "user", "content": user_message})
        return messages

    async def _extract_memories_async(
        self,
        session_id: str,
        user_message: str,
        assistant_message: str,
        user_message_id: str,
        assistant_message_id: str,
    ):
        try:
            if not await self.memory_extractor.should_extract(user_message, assistant_message):
                return
            result = await self.memory_extractor.extract_from_turn(
                user_msg=user_message,
                assistant_msg=assistant_message,
                session_id=session_id,
                user_message_id=user_message_id,
                assistant_message_id=assistant_message_id,
            )
            for memory in result.memories:
                await self.memory_storage.save_memory(memory)
        except Exception:
            pass

    # ---- Session/message APIs for gateway (use SessionStore + StateCache) ----

    async def list_sessions(self, limit: int = 20, offset: int = 0) -> List[Dict[str, Any]]:
        """List session ids with title and updated_at, sorted by updated_at descending."""
        ids = await self.session_store.list_sessions()
        out = []
        for sid in ids:
            meta = await self.session_store.get_session_metadata(sid)
            state = await self.state_cache.load_state(sid)
            updated = (state.updated_at if state else None) or (meta.get("modified") if meta else None) or ""
            out.append({
                "id": sid,
                "title": sid,
                "updated_at": updated,
                "created_at": (meta.get("created_at") if meta else None) or updated,
            })
        out.sort(key=lambda x: x["updated_at"] or "", reverse=True)
        return out[offset : offset + limit]

    async def count_sessions(self) -> int:
        ids = await self.session_store.list_sessions()
        return len(ids)

    async def get_or_create_session(self, session_id: str) -> Dict[str, Any]:
        """Ensure session exists; return {id, title, created_at, updated_at}."""
        state = await self.state_cache.get_or_create_state(session_id)
        return {
            "id": session_id,
            "title": session_id,
            "created_at": state.created_at,
            "updated_at": state.updated_at,
        }

    async def get_session(self, session_id: str) -> Optional[Dict[str, Any]]:
        state = await self.state_cache.load_state(session_id)
        if not state:
            return None
        return {
            "id": session_id,
            "title": session_id,
            "created_at": state.created_at,
            "updated_at": state.updated_at,
        }

    async def load_messages(self, session_id: str, limit: int = 20, offset: int = 0) -> List[Dict[str, Any]]:
        """Return messages as {id, role, content, created_at} from recent turns."""
        state = await self.state_cache.get_or_create_state(session_id)
        turns = state.recent_turns[-(limit + offset) :]
        turns = turns[offset:][:limit]
        out = []
        for t in turns:
            out.append({
                "id": t.user_message_id,
                "role": "user",
                "content": t.user_message,
                "created_at": t.timestamp,
            })
            out.append({
                "id": t.assistant_message_id,
                "role": "assistant",
                "content": t.assistant_message,
                "created_at": t.timestamp,
            })
        return out

    async def create_session(self) -> Dict[str, Any]:
        """Create a new session; returns {id, title, created_at, updated_at}."""
        session_id = f"session-{int(time.time() * 1000)}"
        return await self.get_or_create_session(session_id)


_runtime: Optional[AgentRuntime] = None


async def init_runtime() -> AgentRuntime:
    global _runtime
    _runtime = AgentRuntime()
    await _runtime.initialize()
    return _runtime


def get_runtime() -> AgentRuntime:
    if _runtime is None:
        raise RuntimeError("Runtime not initialized. Call await init_runtime() first.")
    return _runtime
