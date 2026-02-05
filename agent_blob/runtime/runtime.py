from __future__ import annotations

import asyncio
import os
from dataclasses import dataclass
from typing import Any, AsyncIterator, Awaitable, Callable, Dict, Optional

from agent_blob.protocol import EventType, create_event
from agent_blob.policy.policy import Policy
from agent_blob.runtime.storage.event_log import EventLog
from agent_blob.runtime.storage.memory_store import MemoryStore
from agent_blob.runtime.storage.tasks import TaskStore
from agent_blob.runtime.storage.scheduler import SchedulerStore
from agent_blob.runtime.tools.filesystem import filesystem_read, filesystem_list
from agent_blob.runtime.tools.shell import shell_run
from agent_blob.runtime.llm import OpenAIChatCompletionsProvider


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

    async def startup(self):
        await self.event_log.startup()
        await self.memory.startup()
        await self.tasks.startup()
        await self.schedules.startup()
        # Lazily construct provider on first use so the gateway can start even if OPENAI_API_KEY is not set,
        # as long as the user doesn't send an LLM-backed request.

    async def run(
        self,
        *,
        run_id: str,
        user_input: str,
        policy: Policy,
        ask_permission: AskPermission,
    ) -> AsyncIterator[dict]:
        await self.event_log.append({"type": "run.input", "runId": run_id, "input": user_input})
        task_id = await self.tasks.upsert_from_input(run_id=run_id, user_input=user_input)

        yield create_event(EventType.RUN_STATUS, {"runId": run_id, "status": "retrieving_memory"})
        pinned = await self.memory.get_pinned()
        related = await self.memory.search(user_input, limit=5)

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
            await self.event_log.append({"type": "run.output", "runId": run_id, "text": introspection})
            await self.memory.observe_turn(run_id=run_id, user_text=user_input, assistant_text=introspection)
            await self.tasks.mark_done(task_id=task_id)
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

            await self.event_log.append({"type": "run.output", "runId": run_id, "text": response_text})
            await self.memory.observe_turn(run_id=run_id, user_text=user_input, assistant_text=response_text)
        else:
            model = os.getenv("MODEL_NAME", "gpt-4o-mini")
            messages = self._build_messages(user_input=user_input, pinned=pinned, related=related)

            yield create_event(EventType.RUN_STATUS, {"runId": run_id, "status": "streaming"})
            assistant_text = ""
            try:
                if self._llm is None:
                    self._llm = OpenAIChatCompletionsProvider()
                async for tok in self._llm.stream_chat(model=model, messages=messages):
                    assistant_text += tok
                    yield create_event(EventType.RUN_TOKEN, {"runId": run_id, "content": tok})
            except Exception as e:
                await self.event_log.append({"type": "run.error", "runId": run_id, "error": str(e)})
                yield create_event(EventType.RUN_ERROR, {"runId": run_id, "message": str(e)})
                return

            await self.event_log.append({"type": "run.output", "runId": run_id, "text": assistant_text})
            await self.memory.observe_turn(run_id=run_id, user_text=user_input, assistant_text=assistant_text)
        await self.tasks.mark_done(task_id=task_id)

        yield create_event(EventType.RUN_FINAL, {"runId": run_id})

    def _chunk_text(self, text: str, n: int) -> list[str]:
        return [text[i : i + n] for i in range(0, len(text), n)]

    def _build_messages(self, *, user_input: str, pinned: list[dict], related: list[dict]) -> list[dict]:
        system = "You are Agent Blob, a helpful always-on master AI. Be concise and actionable."
        msgs: list[dict] = [{"role": "system", "content": system}]
        if pinned:
            msgs.append({"role": "system", "content": f"Pinned memory (authoritative): {pinned}"})
        if related:
            msgs.append({"role": "system", "content": f"Potentially relevant past notes (may be partial): {related}"})
        msgs.append({"role": "user", "content": user_input})
        return msgs

    async def _maybe_introspect(self, *, user_input: str) -> Optional[str]:
        q = (user_input or "").lower()
        wants_tasks = any(p in q for p in ["what tasks", "tasks running", "what are you doing", "what's running", "what are you working", "background tasks"])
        wants_schedule = any(p in q for p in ["scheduled", "schedule", "reminders", "what's scheduled"])

        if not (wants_tasks or wants_schedule):
            return None

        out = []
        if wants_tasks:
            tasks = await self.tasks.list_tasks()
            active = [t for t in tasks if t.get("status") not in ("done", "cancelled", "failed")]
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
