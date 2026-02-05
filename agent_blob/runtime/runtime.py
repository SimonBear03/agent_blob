from __future__ import annotations

import asyncio
import os
import json
import time
from dataclasses import dataclass
from typing import Any, AsyncIterator, Awaitable, Callable, Dict, Optional, List

from agent_blob.protocol import EventType, create_event
from agent_blob.policy.policy import Policy
from agent_blob.runtime.storage.event_log import EventLog
from agent_blob.runtime.storage.memory_store import MemoryStore
from agent_blob.runtime.storage.tasks import TaskStore
from agent_blob.runtime.storage.scheduler import SchedulerStore
from agent_blob.runtime.tools.filesystem import filesystem_read, filesystem_list
from agent_blob.runtime.tools.shell import shell_run
from agent_blob.runtime.tools.memory import build_memory_tools
from agent_blob.runtime.llm import OpenAIChatCompletionsProvider
from agent_blob.runtime.tools.registry import ToolDefinition, ToolRegistry
from agent_blob.runtime.memory import MemoryExtractor
from agent_blob.config import (
    load_config,
    llm_model_name,
    tasks_attach_window_s,
    tasks_auto_close_after_s,
    memory_embeddings_batch_size,
)


AskPermission = Callable[..., Awaitable[str]]


@dataclass
class ToolContext:
    run_id: str
    policy: Policy
    ask_permission: AskPermission


class Runtime:
    def __init__(self):
        self.event_log = EventLog()
        self.memory = MemoryStore()
        self.tasks = TaskStore()
        self.schedules = SchedulerStore()
        self._llm = None
        self.tools = ToolRegistry(self._default_tools())
        self.memory_extractor = MemoryExtractor()

    async def startup(self):
        await self.event_log.startup()
        await self.memory.startup()
        await self.tasks.startup()
        await self.schedules.startup()
        # Lazily construct provider on first use so the gateway can start even if OPENAI_API_KEY is not set,
        # as long as the user doesn't send an LLM-backed request.

    async def maintenance(self) -> dict:
        """
        Periodic maintenance hook for the supervisor:
        - purge old completed tasks from tasks.json
        - consolidate structured memories incrementally
        - rotate/prune JSONL logs
        """
        cfg = load_config()
        maint = (cfg.get("maintenance") or {}) if isinstance(cfg, dict) else {}
        tasks_cfg = (cfg.get("tasks") or {}) if isinstance(cfg, dict) else {}

        # Auto-close stale tasks so tasks.json doesn't grow unbounded with perpetual open tasks.
        auto_close_after = int(tasks_cfg.get("auto_close_after_s", tasks_auto_close_after_s()) or tasks_auto_close_after_s())
        auto_close_stats = await self.tasks.auto_close_inactive(older_than_s=auto_close_after)
        keep_days = int(maint.get("tasks_keep_done_days", 30) or 30)
        keep_max = int(maint.get("tasks_keep_done_max", 200) or 200)
        purge_stats = await self.tasks.purge_done(keep_days=keep_days, keep_max=keep_max)

        # Consolidate structured candidates into state (cheap incremental).
        added = await self.memory.consolidate()
        # Rotate/prune JSONL logs (best-effort).
        events_rot = await self.event_log.rotate_and_prune()
        tasks_events_rot = await self.tasks.rotate_and_prune_events()
        memories_rot = await self.memory.rotate_and_prune_candidates()
        embedded = 0
        try:
            if self._llm is None and os.getenv("OPENAI_API_KEY"):
                self._llm = OpenAIChatCompletionsProvider()
            if self._llm is not None:
                embedded = await self.memory.embed_pending(llm=self._llm, limit=memory_embeddings_batch_size())
        except Exception:
            embedded = 0
        return {
            "tasks": purge_stats,
            "tasks_autoclosed": auto_close_stats,
            "memory_added": added,
            "logs": {"events": events_rot, "tasks_events": tasks_events_rot, "memories": memories_rot},
            "embeddings_updated": embedded,
        }

    async def _route_task(self, *, run_id: str, user_input: str) -> str:
        """
        Implicit task routing (no /session, no /focus):
        - Attach to most recently updated task within tasks.attach_window_s
        - Otherwise create a new task
        """
        window_s = tasks_attach_window_s()
        recent = await self.tasks.most_recent_within(window_s=window_s, include_terminal=True)
        if isinstance(recent, dict) and recent.get("id"):
            task_id = str(recent["id"])
            await self.tasks.attach_run(task_id=task_id, run_id=run_id)
            return task_id
        return await self.tasks.create_task(run_id=run_id, title=user_input)

    async def run(
        self,
        *,
        run_id: str,
        user_input: str,
        policy: Policy,
        ask_permission: AskPermission,
    ) -> AsyncIterator[dict]:
        task_id = await self._route_task(run_id=run_id, user_input=user_input)
        await self.tasks.set_status(task_id=task_id, status="running")
        await self.event_log.append({"type": "run.input", "runId": run_id, "taskId": task_id, "input": user_input})

        # Explicit memory requests should never be "solved" by writing to repo files or running tools.
        remembered = self._parse_explicit_remember(user_input)
        if remembered is not None:
            reply = f"Got it — I’ll remember: {remembered}"
            yield create_event(EventType.RUN_STATUS, {"runId": run_id, "status": "streaming"})
            for part in self._chunk_text(reply, 240):
                yield create_event(EventType.RUN_TOKEN, {"runId": run_id, "content": part})
                await asyncio.sleep(0)
            await self.event_log.append({"type": "run.output", "runId": run_id, "taskId": task_id, "text": reply})
            # Store a high-importance explicit memory deterministically (no LLM/tool use required).
            await self.memory.save_structured_memories(
                run_id=run_id,
                memories=[
                    {
                        "type": "fact",
                        "content": remembered,
                        "context": "User explicitly asked to remember this.",
                        "importance": 10,
                        "tags": ["explicit"],
                    }
                ],
            )
            await self.tasks.set_status(task_id=task_id, status="open")
            yield create_event(EventType.RUN_FINAL, {"runId": run_id})
            return

        yield create_event(EventType.RUN_STATUS, {"runId": run_id, "status": "retrieving_memory"})
        pinned = await self.memory.get_pinned()
        recent_turns = await self.event_log.recent_turns(limit=8)
        related = await self.event_log.search_turns(user_input, limit=5)
        structured: list[dict]
        try:
            if self._llm is None and os.getenv("OPENAI_API_KEY"):
                self._llm = OpenAIChatCompletionsProvider()
            structured = await self.memory.search_structured_hybrid(query=user_input, limit=5, llm=self._llm)
        except Exception:
            structured = await self.memory.search_structured(user_input, limit=5)

        # Minimal agent loop for V2:
        # - keep explicit smoke-test commands for tools
        # - otherwise use the configured LLM (OpenAI for now) and stream tokens
        yield create_event(EventType.RUN_STATUS, {"runId": run_id, "status": "thinking"})

        tool_ctx = ToolContext(run_id=run_id, policy=policy, ask_permission=ask_permission)

        introspection = await self._maybe_introspect(user_input=user_input)
        if introspection is not None:
            yield create_event(EventType.RUN_STATUS, {"runId": run_id, "status": "streaming"})
            for part in self._chunk_text(introspection, 240):
                yield create_event(EventType.RUN_TOKEN, {"runId": run_id, "content": part})
                await asyncio.sleep(0)
            await self.event_log.append({"type": "run.output", "runId": run_id, "taskId": task_id, "text": introspection})
            await self.memory.observe_turn(run_id=run_id, user_text=user_input, assistant_text=introspection)
            await self.tasks.set_status(task_id=task_id, status="open")
            yield create_event(EventType.RUN_FINAL, {"runId": run_id})
            return

        actions = self._parse_actions(user_input)
        if actions:
            response_text_parts: list[str] = []
            for act in actions:
                kind = act["kind"]
                if kind == "fs.read":
                    out = await self._tool_filesystem_read(tool_ctx, act["path"])
                    response_text_parts.append(out)
                elif kind == "fs.list":
                    out = await self._tool_filesystem_list(tool_ctx, act["path"])
                    response_text_parts.append(out)
                elif kind == "shell":
                    out = await self._tool_shell(tool_ctx, act["command"])
                    response_text_parts.append(out)

            response_text = "".join(response_text_parts)
            yield create_event(EventType.RUN_STATUS, {"runId": run_id, "status": "streaming"})
            for part in self._chunk_text(response_text, 240):
                yield create_event(EventType.RUN_TOKEN, {"runId": run_id, "content": part})
                await asyncio.sleep(0)

            await self.event_log.append({"type": "run.output", "runId": run_id, "taskId": task_id, "text": response_text})
            await self.memory.observe_turn(run_id=run_id, user_text=user_input, assistant_text=response_text)
            mem_stats = await self._extract_and_store_memories(run_id=run_id, user_text=user_input, assistant_text=response_text)
            if mem_stats.get("pinned_added") or mem_stats.get("structured_written"):
                yield create_event(
                    EventType.RUN_LOG,
                    {"runId": run_id, "message": f"memory saved: pinned_added={mem_stats.get('pinned_added')} structured={mem_stats.get('structured_written')}"},
                )
        else:
            model = llm_model_name()
            base_messages = self._build_messages(
                user_input=user_input,
                pinned=pinned,
                related=related,
                structured=structured,
                recent_turns=recent_turns,
            )

            if self._llm is None:
                self._llm = OpenAIChatCompletionsProvider()

            try:
                assistant_text = ""
                async for ev in self._stream_agent_loop_with_tools(
                    run_id=run_id, model=model, messages=base_messages, tool_ctx=tool_ctx
                ):
                    if ev.get("event") == EventType.RUN_TOKEN:
                        assistant_text += (ev.get("payload") or {}).get("content", "")
                    yield ev
            except Exception as e:
                await self.event_log.append({"type": "run.error", "runId": run_id, "taskId": task_id, "error": str(e)})
                await self.tasks.set_status(task_id=task_id, status="open")
                yield create_event(EventType.RUN_ERROR, {"runId": run_id, "message": str(e)})
                return

            await self.event_log.append({"type": "run.output", "runId": run_id, "taskId": task_id, "text": assistant_text})
            await self.memory.observe_turn(run_id=run_id, user_text=user_input, assistant_text=assistant_text)
            mem_stats = await self._extract_and_store_memories(run_id=run_id, user_text=user_input, assistant_text=assistant_text)
            if mem_stats.get("pinned_added") or mem_stats.get("structured_written"):
                yield create_event(
                    EventType.RUN_LOG,
                    {"runId": run_id, "message": f"memory saved: pinned_added={mem_stats.get('pinned_added')} structured={mem_stats.get('structured_written')}"},
                )
        await self.tasks.set_status(task_id=task_id, status="open")

        yield create_event(EventType.RUN_FINAL, {"runId": run_id})

    def _chunk_text(self, text: str, n: int) -> list[str]:
        return [text[i : i + n] for i in range(0, len(text), n)]

    def _build_messages(
        self,
        *,
        user_input: str,
        pinned: list[dict],
        related: list[dict],
        structured: list[dict],
        recent_turns: list[dict],
    ) -> list[dict]:
        system = (
            "You are Agent Blob, a helpful always-on master AI. Be concise and actionable.\n"
            "Never write to project files or run shell commands just to 'remember' something. Use the memory system instead.\n"
            "For memory management, use memory_search/memory_list_recent to find items and memory_delete to remove them.\n"
            "Only use tools when necessary to complete a user-requested task."
        )
        msgs: list[dict] = [{"role": "system", "content": system}]
        if pinned:
            msgs.append({"role": "system", "content": f"Pinned memory (authoritative): {pinned}"})
        if structured:
            msgs.append({"role": "system", "content": f"Structured long-term memories (high confidence): {structured}"})
        if related:
            msgs.append({"role": "system", "content": f"Potentially relevant past notes (may be partial): {related}"})
        for t in recent_turns:
            u = t.get("user")
            a = t.get("assistant")
            if isinstance(u, str) and u:
                msgs.append({"role": "user", "content": u})
            if isinstance(a, str) and a:
                msgs.append({"role": "assistant", "content": a})
        msgs.append({"role": "user", "content": user_input})
        return msgs

    def _parse_explicit_remember(self, user_input: str) -> Optional[str]:
        """
        Parse a user request like:
          "please remember: X"
          "please remember X"
        Returns X or None.
        """
        s = (user_input or "").strip()
        if not s:
            return None
        low = s.lower()
        needle = "please remember"
        if needle not in low:
            return None
        # Take the first occurrence and strip a leading ':' if present.
        idx = low.find(needle)
        tail = s[idx + len(needle) :].strip()
        if tail.startswith(":"):
            tail = tail[1:].strip()
        return tail or None

    async def _extract_and_store_memories(self, *, run_id: str, user_text: str, assistant_text: str) -> dict:
        """
        Best-effort memory extraction. Never fails the run.
        Returns a small stats dict for optional logging.
        """
        stats = {"pinned_added": False, "structured_written": 0, "error": None}
        try:
            if self._llm is None:
                self._llm = OpenAIChatCompletionsProvider()
            memories = await self.memory_extractor.extract(llm=self._llm, user_text=user_text, assistant_text=assistant_text)
            if not memories:
                await self.event_log.append({"type": "memory.extracted", "runId": run_id, "count": 0})
                return stats
            written = await self.memory.save_structured_memories(run_id=run_id, memories=memories)
            stats["structured_written"] = written
            # Update consolidated state (dedupe/merge) incrementally.
            await self.memory.consolidate()
            await self.event_log.append({"type": "memory.extracted", "runId": run_id, "count": written})
        except Exception as e:
            stats["error"] = str(e)
            await self.event_log.append({"type": "memory.extract_error", "runId": run_id, "error": str(e)})
        return stats

    def _default_tools(self) -> List[ToolDefinition]:
        async def _fs_read(args: Dict[str, Any]) -> Any:
            return await filesystem_read(str(args.get("path", "")))

        async def _fs_list(args: Dict[str, Any]) -> Any:
            return await filesystem_list(str(args.get("path", "")))

        async def _shell_run(args: Dict[str, Any]) -> Any:
            return await shell_run(str(args.get("command", "")))

        memory_search, memory_list_recent, memory_delete = build_memory_tools(self.memory)

        return [
            ToolDefinition(
                name="filesystem_read",
                capability="filesystem.read",
                description="Read a text file within the allowed root.",
                parameters={
                    "type": "object",
                    "properties": {"path": {"type": "string", "description": "Path to file"}},
                    "required": ["path"],
                },
                executor=_fs_read,
            ),
            ToolDefinition(
                name="filesystem_list",
                capability="filesystem.list",
                description="List a directory within the allowed root.",
                parameters={
                    "type": "object",
                    "properties": {"path": {"type": "string", "description": "Path to directory"}},
                    "required": ["path"],
                },
                executor=_fs_list,
            ),
            ToolDefinition(
                name="shell_run",
                capability="shell.run",
                description="Run a shell command (requires permission).",
                parameters={
                    "type": "object",
                    "properties": {"command": {"type": "string", "description": "Shell command to run"}},
                    "required": ["command"],
                },
                executor=_shell_run,
            ),
            ToolDefinition(
                name="memory_search",
                capability="memory.search",
                description="Search structured long-term memory items (returns ids you can use to delete).",
                parameters={
                    "type": "object",
                    "properties": {
                        "query": {"type": "string", "description": "Search query"},
                        "limit": {"type": "integer", "description": "Max results", "default": 5},
                    },
                    "required": ["query"],
                },
                executor=memory_search,
            ),
            ToolDefinition(
                name="memory_list_recent",
                capability="memory.list",
                description="List recent structured long-term memory items.",
                parameters={
                    "type": "object",
                    "properties": {"limit": {"type": "integer", "description": "Max results", "default": 20}},
                },
                executor=memory_list_recent,
            ),
            ToolDefinition(
                name="memory_delete",
                capability="memory.delete",
                description="Delete one structured long-term memory item by id (requires permission).",
                parameters={
                    "type": "object",
                    "properties": {"id": {"type": "string", "description": "Memory id from memory_search/list"}},
                    "required": ["id"],
                },
                executor=memory_delete,
            ),
        ]

    async def _stream_agent_loop_with_tools(
        self,
        *,
        run_id: str,
        model: str,
        messages: List[Dict[str, Any]],
        tool_ctx: ToolContext,
        max_rounds: int = 3,
    ) -> AsyncIterator[dict]:
        """
        Streaming tool-calling loop. Caller can reconstruct assistant text by concatenating RUN_TOKEN payloads.
        """
        assert self._llm is not None
        tools = self.tools.to_openai_tools()

        for _round in range(max_rounds):
            tool_calls_dict: Dict[int, Dict[str, Any]] = {}
            assistant_delta_text = ""

            yield create_event(EventType.RUN_STATUS, {"runId": run_id, "status": "streaming"})
            async for chunk in self._llm.stream_chat_chunks(model=model, messages=messages, tools=tools):
                if not getattr(chunk, "choices", None):
                    continue
                delta = chunk.choices[0].delta
                content = getattr(delta, "content", None)
                if content:
                    assistant_delta_text += content
                    yield create_event(EventType.RUN_TOKEN, {"runId": run_id, "content": content})

                if getattr(delta, "tool_calls", None):
                    for tc_chunk in delta.tool_calls:
                        idx = tc_chunk.index
                        if idx not in tool_calls_dict:
                            tool_calls_dict[idx] = {
                                "id": None,
                                "type": "function",
                                "function": {"name": "", "arguments": ""},
                            }
                        if getattr(tc_chunk, "id", None):
                            tool_calls_dict[idx]["id"] = tc_chunk.id
                        fn = getattr(tc_chunk, "function", None)
                        if fn:
                            if getattr(fn, "name", None):
                                tool_calls_dict[idx]["function"]["name"] += fn.name
                            if getattr(fn, "arguments", None):
                                tool_calls_dict[idx]["function"]["arguments"] += fn.arguments or ""

            tool_calls = [tool_calls_dict[i] for i in sorted(tool_calls_dict.keys())]
            if not tool_calls:
                return

            yield create_event(EventType.RUN_STATUS, {"runId": run_id, "status": "executing_tools"})

            # Assistant message that contains tool_calls (required for tool results to be accepted).
            messages = messages + [{"role": "assistant", "content": assistant_delta_text or None, "tool_calls": tool_calls}]

            tool_results_msgs: List[Dict[str, Any]] = []
            for tc in tool_calls:
                tool_call_id = tc.get("id") or f"tool_{run_id}"
                tool_name = tc.get("function", {}).get("name", "")
                raw_args = tc.get("function", {}).get("arguments", "") or ""

                try:
                    args = json.loads(raw_args) if raw_args else {}
                except Exception:
                    args = {}

                try:
                    tool_def = self.tools.get(tool_name)
                except Exception:
                    res = {"ok": False, "error": f"Unknown tool: {tool_name}"}
                    yield create_event(
                        EventType.RUN_TOOL_RESULT,
                        {"runId": run_id, "toolName": tool_name, "ok": False, "result": res},
                    )
                    tool_results_msgs.append({"role": "tool", "tool_call_id": tool_call_id, "content": json.dumps(res)})
                    continue

                yield create_event(EventType.RUN_TOOL_CALL, {"runId": run_id, "toolName": tool_name, "arguments": args})

                await self._enforce(
                    tool_ctx,
                    tool_def.capability,
                    preview=json.dumps(args, ensure_ascii=False),
                    reason=f"Tool call: {tool_def.capability}",
                )

                try:
                    result = await tool_def.executor(args)
                    res = {"ok": True, "result": result}
                except Exception as e:
                    res = {"ok": False, "error": str(e)}

                yield create_event(EventType.RUN_TOOL_RESULT, {"runId": run_id, "toolName": tool_name, **res})
                tool_results_msgs.append(
                    {"role": "tool", "tool_call_id": tool_call_id, "content": json.dumps(res, ensure_ascii=False)}
                )

            messages = messages + tool_results_msgs

        yield create_event(EventType.RUN_LOG, {"runId": run_id, "message": "Reached max tool-calling rounds."})

    async def _maybe_introspect(self, *, user_input: str) -> Optional[str]:
        q = (user_input or "").lower()
        wants_tasks = any(p in q for p in ["what tasks", "tasks running", "what are you doing", "what's running", "what are you working", "background tasks"])
        wants_schedule = any(p in q for p in ["scheduled", "schedule", "reminders", "what's scheduled"])

        if not (wants_tasks or wants_schedule):
            return None

        out = []
        if wants_tasks:
            tasks = await self.tasks.list_tasks()
            now = time.time()
            window_s = tasks_attach_window_s()
            always_active = {"running", "waiting_permission", "waiting_user"}
            active = []
            for t in tasks:
                status = str(t.get("status") or "")
                if status in ("done", "cancelled", "failed"):
                    continue
                updated = float(t.get("updated_at", 0) or 0)
                if status in always_active or (now - updated) <= window_s:
                    active.append(t)
            out.append(f"Active tasks: {len(active)}")
            for t in active[:10]:
                out.append(f"- {t.get('id')}: {t.get('status')} — {t.get('title')}")
            if not active:
                out.append("- (none)")

        if wants_schedule:
            schedules = await self.schedules.list_schedules()
            out.append(f"Scheduled jobs: {len(schedules)}")
            for s in schedules[:10]:
                out.append(f"- {s.get('id','(no id)')}: next_run_at={s.get('next_run_at')}")
            if not schedules:
                out.append("- (none)")

        return "\n".join(out) + "\n"

    def _parse_actions(self, user_input: str) -> list[dict]:
        s = user_input.strip()
        if s.startswith("read "):
            return [{"kind": "fs.read", "path": s[5:].strip()}]
        if s.startswith("ls "):
            return [{"kind": "fs.list", "path": s[3:].strip()}]
        if s.startswith("sh "):
            return [{"kind": "shell", "command": s[3:].strip()}]
        return []

    async def _enforce(self, ctx: ToolContext, capability: str, preview: str, reason: str) -> None:
        decision = ctx.policy.check(capability)
        if decision.decision == "allow":
            return
        if decision.decision == "deny":
            raise PermissionError(f"Denied by policy: {capability}")
        choice = await ctx.ask_permission(run_id=ctx.run_id, capability=capability, preview=preview, reason=reason)
        if choice != "allow":
            raise PermissionError(f"Denied by user: {capability}")

    async def _tool_filesystem_read(self, ctx: ToolContext, path: str) -> str:
        await self._enforce(ctx, "filesystem.read", preview=path, reason="Read file contents")
        res = await filesystem_read(path)
        return f"\n[filesystem.read] {res}\n"

    async def _tool_filesystem_list(self, ctx: ToolContext, path: str) -> str:
        await self._enforce(ctx, "filesystem.list", preview=path, reason="List directory")
        res = await filesystem_list(path)
        return f"\n[filesystem.list] {res}\n"

    async def _tool_shell(self, ctx: ToolContext, command: str) -> str:
        await self._enforce(ctx, "shell.run", preview=command, reason="Run shell command")
        res = await shell_run(command)
        return f"\n[shell.run]\n{res}\n"
