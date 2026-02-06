from __future__ import annotations

from typing import Any, Dict, List

from agent_blob.runtime.capabilities.provider import CapabilityProvider
from agent_blob.runtime.storage.memory_store import MemoryStore
from agent_blob.runtime.tools.filesystem import filesystem_read, filesystem_list, filesystem_write
from agent_blob.runtime.tools.memory import build_memory_tools
from agent_blob.runtime.tools.shell import shell_run
from agent_blob.runtime.tools.web import web_fetch
from agent_blob.runtime.tools.search import fs_glob, fs_grep
from agent_blob.runtime.tools.edit import edit_apply_patch
from agent_blob.runtime.tools.registry import ToolDefinition


class LocalProvider:
    name = "local"

    def __init__(self, *, memory: MemoryStore, schedules):
        self.memory = memory
        self.schedules = schedules

    def tools(self) -> List[ToolDefinition]:
        async def _fs_read(args: Dict[str, Any]) -> Any:
            return await filesystem_read(str(args.get("path", "")))

        async def _fs_list(args: Dict[str, Any]) -> Any:
            return await filesystem_list(str(args.get("path", "")))

        async def _fs_write(args: Dict[str, Any]) -> Any:
            return await filesystem_write(
                str(args.get("path", "")),
                str(args.get("content", "")),
                append=bool(args.get("append", False)),
                create_parents=bool(args.get("create_parents", True)),
            )

        async def _shell_run(args: Dict[str, Any]) -> Any:
            return await shell_run(str(args.get("command", "")))

        async def _web_fetch(args: Dict[str, Any]) -> Any:
            return await web_fetch(
                str(args.get("url", "")),
                max_bytes=int(args.get("max_bytes", 1_000_000) or 1_000_000),
                timeout_s=float(args.get("timeout_s", 15.0) or 15.0),
            )

        async def _fs_glob(args: Dict[str, Any]) -> Any:
            return await fs_glob(
                pattern=str(args.get("pattern", "")),
                base_dir=str(args.get("base_dir", ".")),
                limit=int(args.get("limit", 200) or 200),
            )

        async def _fs_grep(args: Dict[str, Any]) -> Any:
            return await fs_grep(
                query=str(args.get("query", "")),
                base_dir=str(args.get("base_dir", ".")),
                limit=int(args.get("limit", 50) or 50),
            )

        async def _edit_apply_patch(args: Dict[str, Any]) -> Any:
            return await edit_apply_patch(
                path=str(args.get("path", "")),
                patch=str(args.get("patch", "")),
                create_parents=bool(args.get("create_parents", True)),
            )

        async def _schedule_list(args: Dict[str, Any]) -> Any:
            await self.schedules.startup()
            return {"ok": True, "schedules": await self.schedules.list_schedules()}

        async def _schedule_create_interval(args: Dict[str, Any]) -> Any:
            await self.schedules.startup()
            prompt = args.get("prompt")
            if prompt is None:
                prompt = args.get("input", "")
            if not str(prompt or "").strip():
                return {"ok": False, "error": "Missing prompt (what should the agent do when the schedule runs?)"}
            rec = await self.schedules.create_interval(
                input=str(prompt or ""),
                interval_s=int(args.get("interval_s", 60) or 60),
                enabled=bool(args.get("enabled", True)),
                title=str(args.get("title", "") or "") or None,
            )
            return {"ok": True, "schedule": rec}

        async def _schedule_create_daily(args: Dict[str, Any]) -> Any:
            await self.schedules.startup()
            prompt = args.get("prompt")
            if prompt is None:
                prompt = args.get("input", "")
            if not str(prompt or "").strip():
                return {"ok": False, "error": "Missing prompt (what should the agent do when the schedule runs?)"}
            rec = await self.schedules.create_daily(
                input=str(prompt or ""),
                hour=int(args.get("hour", 7) or 7),
                minute=int(args.get("minute", 30) or 30),
                tz=(str(args.get("tz")).strip() if args.get("tz") is not None else None),
                enabled=bool(args.get("enabled", True)),
                title=str(args.get("title", "") or "") or None,
            )
            return {"ok": True, "schedule": rec}

        async def _schedule_create_cron(args: Dict[str, Any]) -> Any:
            await self.schedules.startup()
            prompt = args.get("prompt")
            if prompt is None:
                prompt = args.get("input", "")
            if not str(prompt or "").strip():
                return {"ok": False, "error": "Missing prompt (what should the agent do when the schedule runs?)"}
            rec = await self.schedules.create_cron(
                input=str(prompt or ""),
                cron=str(args.get("cron", "") or ""),
                tz=(str(args.get("tz")).strip() if args.get("tz") is not None else None),
                enabled=bool(args.get("enabled", True)),
                title=str(args.get("title", "") or "") or None,
            )
            return {"ok": True, "schedule": rec}

        async def _schedule_delete(args: Dict[str, Any]) -> Any:
            await self.schedules.startup()
            return await self.schedules.delete(schedule_id=str(args.get("id", "") or ""))

        async def _schedule_set_enabled(args: Dict[str, Any]) -> Any:
            await self.schedules.startup()
            return await self.schedules.set_enabled(
                schedule_id=str(args.get("id", "") or ""),
                enabled=bool(args.get("enabled", True)),
            )

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
                name="fs_glob",
                capability="filesystem.glob",
                description="Find files by glob pattern under the allowed root (safe).",
                parameters={
                    "type": "object",
                    "properties": {
                        "pattern": {"type": "string", "description": "Glob pattern like **/*.py"},
                        "base_dir": {"type": "string", "description": "Base directory", "default": "."},
                        "limit": {"type": "integer", "description": "Max matches", "default": 200},
                    },
                    "required": ["pattern"],
                },
                executor=_fs_glob,
            ),
            ToolDefinition(
                name="fs_grep",
                capability="filesystem.grep",
                description="Search for text under the allowed root (safe).",
                parameters={
                    "type": "object",
                    "properties": {
                        "query": {"type": "string", "description": "Substring query"},
                        "base_dir": {"type": "string", "description": "Base directory", "default": "."},
                        "limit": {"type": "integer", "description": "Max results", "default": 50},
                    },
                    "required": ["query"],
                },
                executor=_fs_grep,
            ),
            ToolDefinition(
                name="edit_apply_patch",
                capability="filesystem.write",
                description="Preferred for modifying existing files: apply a unified diff patch (requires permission).",
                parameters={
                    "type": "object",
                    "properties": {
                        "path": {"type": "string", "description": "Path to file"},
                        "patch": {"type": "string", "description": "Unified diff patch"},
                        "create_parents": {"type": "boolean", "description": "Create parent dirs", "default": True},
                    },
                    "required": ["path", "patch"],
                },
                executor=_edit_apply_patch,
            ),
            ToolDefinition(
                name="filesystem_write",
                capability="filesystem.write",
                description="Write/overwrite a full text file (requires permission). Prefer edit_apply_patch for edits to existing files.",
                parameters={
                    "type": "object",
                    "properties": {
                        "path": {"type": "string", "description": "Path to file"},
                        "content": {"type": "string", "description": "Full file content to write"},
                        "append": {"type": "boolean", "description": "Append instead of overwrite", "default": False},
                        "create_parents": {"type": "boolean", "description": "Create parent dirs", "default": True},
                    },
                    "required": ["path", "content"],
                },
                executor=_fs_write,
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
                name="web_fetch",
                capability="web.fetch",
                description="Fetch a URL (GET) and return text content (requires permission).",
                parameters={
                    "type": "object",
                    "properties": {
                        "url": {"type": "string", "description": "http(s) URL"},
                        "max_bytes": {"type": "integer", "description": "Max bytes to read", "default": 1000000},
                        "timeout_s": {"type": "number", "description": "Request timeout seconds", "default": 15},
                    },
                    "required": ["url"],
                },
                executor=_web_fetch,
            ),
            ToolDefinition(
                name="schedule_list",
                capability="schedules.list",
                description="List schedules (interval-based) that can trigger background runs.",
                parameters={"type": "object", "properties": {}},
                executor=_schedule_list,
            ),
            ToolDefinition(
                name="schedule_create_interval",
                capability="schedules.write",
                description="Create an interval schedule that triggers a run every N seconds.",
                parameters={
                    "type": "object",
                    "properties": {
                        "prompt": {"type": "string", "description": "What the agent should do when the schedule runs"},
                        "input": {"type": "string", "description": "(Deprecated) alias for prompt"},
                        "interval_s": {"type": "integer", "description": "Interval in seconds", "default": 3600},
                        "enabled": {"type": "boolean", "description": "Whether the schedule is active", "default": True},
                        "title": {"type": "string", "description": "Optional short title"},
                    },
                    "required": ["interval_s"],
                },
                executor=_schedule_create_interval,
            ),
            ToolDefinition(
                name="schedule_create_daily",
                capability="schedules.write",
                description="Create a daily schedule at a specific local time (hour/minute).",
                parameters={
                    "type": "object",
                    "properties": {
                        "prompt": {"type": "string", "description": "What the agent should do when the schedule runs"},
                        "input": {"type": "string", "description": "(Deprecated) alias for prompt"},
                        "hour": {"type": "integer", "description": "Hour (0-23)"},
                        "minute": {"type": "integer", "description": "Minute (0-59)"},
                        "tz": {"type": "string", "description": "IANA timezone, e.g. America/Los_Angeles (optional)"},
                        "enabled": {"type": "boolean", "description": "Whether the schedule is active", "default": True},
                        "title": {"type": "string", "description": "Optional short title"},
                    },
                    "required": ["hour", "minute"],
                },
                executor=_schedule_create_daily,
            ),
            ToolDefinition(
                name="schedule_create_cron",
                capability="schedules.write",
                description="Create a cron schedule (5-field: min hour dom mon dow).",
                parameters={
                    "type": "object",
                    "properties": {
                        "prompt": {"type": "string", "description": "What the agent should do when the schedule runs"},
                        "input": {"type": "string", "description": "(Deprecated) alias for prompt"},
                        "cron": {"type": "string", "description": "Cron expression: min hour dom mon dow"},
                        "tz": {"type": "string", "description": "IANA timezone, e.g. America/New_York (optional)"},
                        "enabled": {"type": "boolean", "description": "Whether the schedule is active", "default": True},
                        "title": {"type": "string", "description": "Optional short title"},
                    },
                    "required": ["cron"],
                },
                executor=_schedule_create_cron,
            ),
            ToolDefinition(
                name="schedule_delete",
                capability="schedules.write",
                description="Delete a schedule by id.",
                parameters={
                    "type": "object",
                    "properties": {"id": {"type": "string", "description": "Schedule id"}},
                    "required": ["id"],
                },
                executor=_schedule_delete,
            ),
            ToolDefinition(
                name="schedule_update",
                capability="schedules.write",
                description="Update a schedule (enable/disable).",
                parameters={
                    "type": "object",
                    "properties": {
                        "id": {"type": "string", "description": "Schedule id"},
                        "enabled": {"type": "boolean", "description": "Whether the schedule is enabled"},
                    },
                    "required": ["id", "enabled"],
                },
                executor=_schedule_set_enabled,
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

    def system_instructions(self) -> str | None:
        return None
