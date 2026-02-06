from __future__ import annotations

import asyncio
import os
import json
import time
import difflib
import re
from uuid import uuid4
from dataclasses import dataclass
from typing import Any, AsyncIterator, Awaitable, Callable, Dict, Optional, List

from agent_blob.protocol import EventType, create_event
from agent_blob.policy.policy import Policy
from agent_blob.runtime.storage.event_log import EventLog
from agent_blob.runtime.storage.memory_store import MemoryStore
from agent_blob.runtime.storage.tasks import TaskStore
from agent_blob.runtime.storage.scheduler import SchedulerStore
from agent_blob.runtime.llm import OpenAIChatCompletionsProvider
from agent_blob.runtime.tools.registry import ToolDefinition, ToolRegistry
from agent_blob.runtime.memory import MemoryExtractor
from agent_blob.runtime.capabilities.registry import CapabilityRegistry
from agent_blob.runtime.providers import LocalProvider, SkillsProvider, MCPProvider, WorkersProvider
from agent_blob.runtime.tools.filesystem import filesystem_read_optional
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
        self._active_workers: Dict[str, Dict[str, Any]] = {}
        self.capabilities = CapabilityRegistry(
            providers=[
                LocalProvider(memory=self.memory, schedules=self.schedules),
                SkillsProvider(),
                MCPProvider(),
                WorkersProvider(),
            ]
        )
        tool_defs = self.capabilities.tools()
        self._tool_defs_by_name = {t.name: t for t in tool_defs}
        self.tools = ToolRegistry(tool_defs)
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
        raw_input = str(user_input or "")
        scheduled_id = None
        m = re.match(r"^\[scheduled:([^\]]+)\]\s*(.*)$", raw_input.strip(), flags=re.IGNORECASE | re.DOTALL)
        if m:
            scheduled_id = m.group(1).strip()
            # Strip the scheduled prefix for the LLM/user-visible intent.
            user_input = m.group(2).strip()

        if scheduled_id:
            task_id = await self.tasks.ensure_task(task_id=f"task_sched_{scheduled_id}", title=f"scheduled:{scheduled_id}")
            await self.tasks.attach_run(task_id=task_id, run_id=run_id)
        else:
            task_id = await self._route_task(run_id=run_id, user_input=user_input)
        await self.tasks.set_status(task_id=task_id, status="running")
        await self.event_log.append(
            {
                "type": "run.input",
                "runId": run_id,
                "taskId": task_id,
                "input": user_input,
                "source": {"kind": "schedule", "id": scheduled_id} if scheduled_id else {"kind": "user"},
            }
        )

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

        model = llm_model_name()
        base_messages = self._build_messages(
            user_input=user_input,
            pinned=pinned,
            related=related,
            structured=structured,
            recent_turns=recent_turns,
            scheduled_id=scheduled_id,
        )

        if self._llm is None:
            self._llm = OpenAIChatCompletionsProvider()

        try:
            assistant_text = ""
            async for ev in self._stream_agent_loop_with_tools(run_id=run_id, model=model, messages=base_messages, tool_ctx=tool_ctx):
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
        scheduled_id: str | None = None,
    ) -> list[dict]:
        system = (
            "You are Agent Blob, a helpful always-on master AI. Be concise and actionable.\n"
            "Never write to project files or run shell commands just to 'remember' something. Use the memory system instead.\n"
            "For memory management, use memory_search/memory_list_recent to find items and memory_delete to remove them.\n"
            "For file edits, prefer fs_glob/fs_grep/filesystem_read to locate the right file, then use edit_apply_patch for changes.\n"
            "Use filesystem_write primarily for creating new files or full overwrites; use edit_apply_patch for modifying existing files.\n"
            "For scheduling background jobs, use schedule_create_interval, schedule_list, and schedule_delete.\n"
            "For wall-clock schedules, prefer schedule_create_daily or schedule_create_cron (cron uses min hour dom mon dow) and include an IANA timezone when possible.\n"
            "To pause/resume a schedule, use schedule_update (enabled=true/false).\n"
            "For multitasking, you may delegate to specialized workers via worker_run (briefing/quant/dev) and then report the result to the user.\n"
            "Do NOT use shell_run to modify files (e.g. '>', '>>', 'tee', 'sed -i'). Use filesystem_write or edit_apply_patch.\n"
            "Only use tools when necessary to complete a user-requested task."
        )
        cap_instructions = self.capabilities.system_instructions()
        if cap_instructions:
            system = system + "\n\n" + cap_instructions.strip()
        msgs: list[dict] = [{"role": "system", "content": system}]
        if scheduled_id:
            msgs.append(
                {
                    "role": "system",
                    "content": (
                        f"This message was triggered by a schedule (id={scheduled_id}).\n"
                        "Execute the scheduled prompt now.\n"
                        "Do not suggest \"I can help you set up a schedule\"—the schedule already exists.\n"
                        "If the prompt requires tools (shell/filesystem/MCP), call the appropriate tools."
                    ),
                }
            )
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

                # Lightweight schema validation: if required args are missing, don't ask permission or execute.
                required = []
                try:
                    required = list((tool_def.parameters or {}).get("required") or [])
                except Exception:
                    required = []
                missing = [k for k in required if k not in args]
                if missing:
                    res = {"ok": False, "error": f"Missing required arguments: {missing}", "missing": missing}
                    yield create_event(EventType.RUN_TOOL_RESULT, {"runId": run_id, "toolName": tool_name, **res})
                    tool_results_msgs.append(
                        {"role": "tool", "tool_call_id": tool_call_id, "content": json.dumps(res, ensure_ascii=False)}
                    )
                    continue

                preview = json.dumps(args, ensure_ascii=False)
                # For file writes, show a unified diff instead of raw JSON arguments.
                if tool_def.capability == "filesystem.write":
                    if tool_def.name == "edit_apply_patch":
                        preview = await self._preview_edit_apply_patch(args)
                    else:
                        preview = await self._preview_filesystem_write(args)

                effective_capability = tool_def.capability
                # Treat shell commands that modify files as a separate high-risk capability, so users can
                # allow `shell.run` for safe read-only commands but still be prompted for writes.
                if tool_def.capability == "shell.run":
                    cmd = str(args.get("command", "") or "")
                    if self._shell_command_writes_files(cmd):
                        effective_capability = "shell.write"

                await self._enforce(
                    tool_ctx,
                    effective_capability,
                    preview=preview,
                    reason=f"Tool call: {effective_capability}",
                )

                try:
                    if tool_def.name == "worker_run":
                        res = await self._execute_worker_run(args=args, tool_ctx=tool_ctx)
                    else:
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

    async def _execute_worker_run(self, *, args: Dict[str, Any], tool_ctx: ToolContext) -> Dict[str, Any]:
        worker_type = str(args.get("worker_type", "") or "").strip().lower()
        prompt = str(args.get("prompt", "") or "").strip()
        max_rounds = int(args.get("max_rounds", 3) or 3)
        if not worker_type or not prompt:
            return {"ok": False, "error": "worker_type and prompt are required"}

        worker_run_id = f"run_worker_{uuid4().hex[:10]}"
        self._active_workers[worker_run_id] = {
            "workerRunId": worker_run_id,
            "workerType": worker_type,
            "parentRunId": tool_ctx.run_id,
            "started_at": time.time(),
            "status": "running",
        }
        await self.event_log.append(
            {
                "type": "worker.spawn",
                "runId": tool_ctx.run_id,
                "workerRunId": worker_run_id,
                "workerType": worker_type,
            }
        )

        # Bubble permissions to the user under the worker run id.
        wctx = ToolContext(run_id=worker_run_id, policy=tool_ctx.policy, ask_permission=tool_ctx.ask_permission)

        # Pick tool subset by worker type.
        if worker_type == "briefing":
            allowed = {"web_fetch"}
            system = (
                "You are a briefing worker. Execute the user's prompt by gathering information if needed and returning a concise result.\n"
                "You may use web_fetch when necessary. Be concise.\n"
            )
        elif worker_type == "quant":
            allowed = {"mcp_list_servers", "mcp_list_tools", "mcp_refresh", "mcp_call", "mcp_list_prompts", "mcp_get_prompt"}
            system = (
                "You are a quant worker. Execute the user's prompt by calling MCP tools as needed and returning a concise result.\n"
                "Prefer querying state (positions/risk) over making changes.\n"
            )
        elif worker_type == "dev":
            allowed = {"fs_glob", "fs_grep", "filesystem_read", "edit_apply_patch", "filesystem_write"}
            system = (
                "You are a dev worker. Execute the user's prompt using filesystem search/read and patch-based edits.\n"
                "Prefer edit_apply_patch for modifications.\n"
            )
        else:
            return {"ok": False, "error": f"Unknown worker_type: {worker_type}"}

        tool_defs = []
        for name in sorted(allowed):
            t = self._tool_defs_by_name.get(name)
            if t:
                tool_defs.append(t)

        worker_tools = ToolRegistry(tool_defs)
        worker_messages = [{"role": "system", "content": system}, {"role": "user", "content": prompt}]

        if self._llm is None:
            self._llm = OpenAIChatCompletionsProvider()
        model = llm_model_name()

        out_text = await self._run_agent_loop_collect_text(
            run_id=worker_run_id,
            model=model,
            messages=worker_messages,
            tool_ctx=wctx,
            tools_registry=worker_tools,
            max_rounds=max(1, min(10, max_rounds)),
        )
        await self.event_log.append(
            {
                "type": "worker.done",
                "runId": tool_ctx.run_id,
                "workerRunId": worker_run_id,
                "workerType": worker_type,
            }
        )
        if worker_run_id in self._active_workers:
            self._active_workers[worker_run_id]["status"] = "done"
            self._active_workers[worker_run_id]["finished_at"] = time.time()
            self._active_workers[worker_run_id]["output_len"] = len(out_text or "")
            # Keep it for a short time for introspection, but don't grow unbounded.
            # Simple cap: keep most recent 50 records (running or done).
            if len(self._active_workers) > 50:
                # Drop oldest finished workers first.
                finished = [
                    (float(v.get("finished_at", 0) or 0), k)
                    for k, v in self._active_workers.items()
                    if isinstance(v, dict) and v.get("status") == "done"
                ]
                finished.sort()
                for _, k in finished[: max(0, len(self._active_workers) - 50)]:
                    self._active_workers.pop(k, None)
        return {"ok": True, "result": {"workerRunId": worker_run_id, "workerType": worker_type, "output": out_text}}

    async def _run_agent_loop_collect_text(
        self,
        *,
        run_id: str,
        model: str,
        messages: List[Dict[str, Any]],
        tool_ctx: ToolContext,
        tools_registry: ToolRegistry,
        max_rounds: int,
    ) -> str:
        """
        Run a tool-calling loop but collect the assistant output as text (no streaming events).
        Used for worker delegation.
        """
        assert self._llm is not None
        tools = tools_registry.to_openai_tools()
        final_text = ""

        for _round in range(max_rounds):
            tool_calls_dict: Dict[int, Dict[str, Any]] = {}
            assistant_delta_text = ""
            async for chunk in self._llm.stream_chat_chunks(model=model, messages=messages, tools=tools):
                if not getattr(chunk, "choices", None):
                    continue
                delta = chunk.choices[0].delta
                content = getattr(delta, "content", None)
                if content:
                    assistant_delta_text += content
                if getattr(delta, "tool_calls", None):
                    for tc_chunk in delta.tool_calls:
                        idx = tc_chunk.index
                        if idx not in tool_calls_dict:
                            tool_calls_dict[idx] = {"id": None, "type": "function", "function": {"name": "", "arguments": ""}}
                        if getattr(tc_chunk, "id", None):
                            tool_calls_dict[idx]["id"] = tc_chunk.id
                        fn = getattr(tc_chunk, "function", None)
                        if fn:
                            if getattr(fn, "name", None):
                                tool_calls_dict[idx]["function"]["name"] += fn.name
                            if getattr(fn, "arguments", None):
                                tool_calls_dict[idx]["function"]["arguments"] += fn.arguments or ""

            tool_calls = [tool_calls_dict[i] for i in sorted(tool_calls_dict.keys())]
            final_text = assistant_delta_text.strip() or final_text
            if not tool_calls:
                return final_text

            # Append assistant tool_calls message
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

                # Disallow nested delegation for now.
                if tool_name == "worker_run":
                    res = {"ok": False, "error": "Nested worker_run is not supported"}
                    tool_results_msgs.append({"role": "tool", "tool_call_id": tool_call_id, "content": json.dumps(res)})
                    continue

                try:
                    tool_def = tools_registry.get(tool_name)
                except Exception:
                    res = {"ok": False, "error": f"Unknown worker tool: {tool_name}"}
                    tool_results_msgs.append({"role": "tool", "tool_call_id": tool_call_id, "content": json.dumps(res)})
                    continue

                required = []
                try:
                    required = list((tool_def.parameters or {}).get("required") or [])
                except Exception:
                    required = []
                missing = [k for k in required if k not in args]
                if missing:
                    res = {"ok": False, "error": f"Missing required arguments: {missing}", "missing": missing}
                    tool_results_msgs.append({"role": "tool", "tool_call_id": tool_call_id, "content": json.dumps(res)})
                    continue

                preview = json.dumps(args, ensure_ascii=False)
                if tool_def.capability == "filesystem.write":
                    if tool_def.name == "edit_apply_patch":
                        preview = await self._preview_edit_apply_patch(args)
                    else:
                        preview = await self._preview_filesystem_write(args)

                effective_capability = tool_def.capability
                if tool_def.capability == "shell.run":
                    cmd = str(args.get("command", "") or "")
                    if self._shell_command_writes_files(cmd):
                        effective_capability = "shell.write"

                await self._enforce(tool_ctx, effective_capability, preview=preview, reason=f"Worker tool call: {effective_capability}")

                try:
                    result = await tool_def.executor(args)
                    res = {"ok": True, "result": result}
                except Exception as e:
                    res = {"ok": False, "error": str(e)}

                tool_results_msgs.append(
                    {"role": "tool", "tool_call_id": tool_call_id, "content": json.dumps(res, ensure_ascii=False)}
                )

            messages = messages + tool_results_msgs

        return final_text

    def _shell_command_writes_files(self, command: str) -> bool:
        """
        Heuristic: commands that likely modify files should require a stronger approval signal.
        This mirrors the "prefer patch-based edits" behavior in Codex/Claude-style tools.
        """
        s = (command or "").strip()
        if not s:
            return False

        # Redirections almost always imply file writes.
        if ">>" in s or ">" in s:
            return True

        # Common write-ish patterns.
        patterns = [
            r"\btee\b",  # often used to write files (even without redirection)
            r"\bsed\s+-i\b",
            r"\bperl\s+-pi\b",
            r"\brm\b",
            r"\bmv\b",
            r"\bcp\b",
            r"\btruncate\b",
            r"\btouch\b",
            r"\bchmod\b",
            r"\bchown\b",
            r"\bgit\s+commit\b",
            r"\bgit\s+push\b",
            r"\bgit\s+reset\b",
            r"\bgit\s+checkout\b",
            r"\bgit\s+switch\b",
            r"\bgit\s+clean\b",
        ]
        for pat in patterns:
            if re.search(pat, s):
                return True
        return False

    async def _preview_filesystem_write(self, args: Dict[str, Any]) -> str:
        path = str(args.get("path", "") or "")
        new = str(args.get("content", "") or "")
        append = bool(args.get("append", False))
        old_res = await filesystem_read_optional(path)
        if not old_res.get("ok"):
            return json.dumps({"path": path, "error": old_res.get("error")}, ensure_ascii=False)
        old = str(old_res.get("content", "") or "")
        if append:
            # Mirror filesystem_write() behavior: ensure newline when appending to non-empty file.
            to_write = new
            if old and (not old.endswith("\n")) and to_write and (not to_write.startswith("\n")):
                to_write = "\n" + to_write
            old_for_diff = old
            new_for_diff = old + to_write
        else:
            old_for_diff = old
            new_for_diff = new
        diff = difflib.unified_diff(
            old_for_diff.splitlines(keepends=True),
            new_for_diff.splitlines(keepends=True),
            fromfile=f"a/{path}",
            tofile=f"b/{path}",
            n=3,
        )
        text = "".join(diff)
        if not text:
            text = f"(no changes) path={path}"
        # Hard cap preview size
        if len(text) > 8000:
            text = text[:8000] + "\n... (truncated)\n"
        return text

    async def _preview_edit_apply_patch(self, args: Dict[str, Any]) -> str:
        path = str(args.get("path", "") or "")
        patch = str(args.get("patch", "") or "")
        if not path or not patch:
            return json.dumps({"path": path, "error": "path and patch are required"}, ensure_ascii=False)
        from agent_blob.runtime.tools.edit import edit_preview_patch

        res = await edit_preview_patch(path=path, patch=patch)
        if not res.get("ok"):
            return json.dumps({"path": path, "error": res.get("error")}, ensure_ascii=False)
        text = str(res.get("preview", "") or "")
        if not text:
            text = f"(no changes) path={path}"
        if len(text) > 8000:
            text = text[:8000] + "\n... (truncated)\n"
        return text

    async def _maybe_introspect(self, *, user_input: str) -> Optional[str]:
        q = (user_input or "").lower()
        wants_tasks = any(p in q for p in ["what tasks", "tasks running", "what are you doing", "what's running", "what are you working", "background tasks"])
        # Only treat schedules as "introspection" for status-style queries.
        # If the user is asking to create/update/delete a schedule, we should NOT short-circuit the agent loop;
        # the LLM should use schedule_create_interval/schedule_delete tools instead.
        wants_schedule = any(p in q for p in ["scheduled", "what's scheduled", "list schedules", "show schedules", "scheduled jobs", "my schedules"])
        schedule_action = any(
            p in q
            for p in [
                "create a schedule",
                "create schedule",
                "add a schedule",
                "add schedule",
                "set up a schedule",
                "setup a schedule",
                "schedule me",
                "delete schedule",
                "remove schedule",
                "update schedule",
                "change schedule",
                "every ",
                "interval",
            ]
        )
        if schedule_action:
            wants_schedule = False
        wants_memory = any(
            p in q
            for p in [
                "what do you remember",
                "what do you remember from our conversation",
                "what did we talk about",
                "list memories",
                "recent memories",
                "show memories",
            ]
        )
        wants_memory_query = any(
            p in q
            for p in [
                "do you remember",
                "did you remember",
                "did we decide",
                "what did we decide",
                "what did we agree",
                "what did we agree on",
                "what did we say about",
                "do you recall",
                "did we talk about",
            ]
        )
        wants_workers = any(
            p in q
            for p in [
                "workers active",
                "any workers",
                "any worker",
                "running workers",
                "active workers",
                "sub agent",
                "sub-agent",
                "subagent",
                "sub agents",
                "delegated",
                "delegation",
                "child run",
                "worker run",
            ]
        )

        if not (wants_tasks or wants_schedule or wants_memory or wants_memory_query or wants_workers):
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

        if wants_memory:
            pinned = await self.memory.get_pinned()
            recent = await self.memory.list_recent_structured(limit=10)
            out.append(f"Pinned memory items: {len(pinned)}")
            for p in pinned[:10]:
                if isinstance(p, dict):
                    out.append(f"- {p.get('content')}")
            if not pinned:
                out.append("- (none)")
            out.append(f"Recent structured memories: {len(recent)}")
            for m in recent[:10]:
                if isinstance(m, dict):
                    out.append(f"- ({m.get('type')}) {m.get('content')}")
            if not recent:
                out.append("- (none)")

        if wants_memory_query and not wants_memory:
            # For recall questions, actually search long-term memory (not just "recent").
            try:
                if self._llm is None and os.getenv("OPENAI_API_KEY"):
                    self._llm = OpenAIChatCompletionsProvider()
                results = await self.memory.search_structured_hybrid(query=user_input, limit=10, llm=self._llm)
            except Exception:
                results = await self.memory.search_structured(user_input, limit=10)
            out.append("Memory search results:")
            if results:
                for m in results[:10]:
                    if isinstance(m, dict):
                        out.append(f"- ({m.get('type')}) {m.get('content')}")
            else:
                out.append("- (no matches)")
                out.append("Tip: try a couple more keywords (project name, module name, date).")

        if wants_workers:
            rows = list(self._active_workers.values())
            running = [r for r in rows if isinstance(r, dict) and r.get("status") == "running"]
            out.append(f"Active workers: {len(running)}")
            for r in running[:10]:
                out.append(f"- {r.get('workerRunId')}: {r.get('workerType')} (parent={r.get('parentRunId')})")
            if not running:
                out.append("- (none)")

        return "\n".join(out) + "\n"

    async def _enforce(self, ctx: ToolContext, capability: str, preview: str, reason: str) -> None:
        decision = ctx.policy.check(capability)
        if decision.decision == "allow":
            return
        if decision.decision == "deny":
            raise PermissionError(f"Denied by policy: {capability}")
        choice = await ctx.ask_permission(run_id=ctx.run_id, capability=capability, preview=preview, reason=reason)
        if choice != "allow":
            raise PermissionError(f"Denied by user: {capability}")
