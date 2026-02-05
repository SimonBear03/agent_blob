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

    def __init__(self, *, memory: MemoryStore):
        self.memory = memory

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
                description="Apply a unified diff patch to a file (requires permission).",
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
                description="Write a text file within the allowed root (requires permission).",
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
