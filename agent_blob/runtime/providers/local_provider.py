from __future__ import annotations

from typing import Any, Dict, List

from agent_blob.runtime.capabilities.provider import CapabilityProvider
from agent_blob.runtime.storage.memory_store import MemoryStore
from agent_blob.runtime.tools.filesystem import filesystem_read, filesystem_list
from agent_blob.runtime.tools.memory import build_memory_tools
from agent_blob.runtime.tools.shell import shell_run
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

    def system_instructions(self) -> str | None:
        return None

