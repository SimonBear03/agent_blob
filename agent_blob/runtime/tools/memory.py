from __future__ import annotations

from typing import Any, Dict

from agent_blob.runtime.memory.service import MemoryService


def build_memory_tools(memory: MemoryService):
    async def memory_search(args: Dict[str, Any]) -> Any:
        query = str(args.get("query", "") or "").strip()
        limit = int(args.get("limit", 5) or 5)
        return await memory.search(query=query, limit=limit)

    async def memory_list_recent(args: Dict[str, Any]) -> Any:
        limit = int(args.get("limit", 20) or 20)
        return await memory.list_recent(limit=limit)

    async def memory_delete(args: Dict[str, Any]) -> Any:
        mem_id = str(args.get("id", "") or "").strip()
        run_id = str(args.get("_run_id", "") or "").strip() or None
        return await memory.delete(memory_id=mem_id, run_id=run_id)

    return memory_search, memory_list_recent, memory_delete
