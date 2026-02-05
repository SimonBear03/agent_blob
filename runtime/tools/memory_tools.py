"""
Memory management tools for pinned memory operations.
Uses an in-memory store (no runtime.db dependency).
"""
from typing import Optional
from . import ToolDefinition, ToolRegistry

# In-memory store for pinned memories: key -> {"value", "description"}
_pinned: dict[str, dict] = {}


def _get_memory(key: str) -> dict | None:
    raw = _pinned.get(key)
    if raw is None:
        return None
    return {"key": key, "value": raw["value"], "description": raw.get("description")}


def _set_memory(key: str, value: str, description: Optional[str] = None) -> dict:
    _pinned[key] = {"value": value, "description": description}
    return _get_memory(key)


def _delete_memory(key: str) -> None:
    _pinned.pop(key, None)


async def get_memory(key: str) -> dict:
    """
    Get a pinned memory entry by key.

    Args:
        key: The memory key to retrieve

    Returns:
        Dict with 'success', 'memory'/'error'
    """
    try:
        memory = _get_memory(key)
        if memory:
            return {"success": True, "memory": memory}
        return {"success": False, "error": f"Memory with key '{key}' not found"}
    except Exception as e:
        return {"success": False, "error": f"Error retrieving memory: {e!s}"}


async def set_memory(key: str, value: str, description: Optional[str] = None) -> dict:
    """
    Set or update a pinned memory entry.

    Args:
        key: The memory key
        value: The memory value
        description: Optional description of what this memory represents

    Returns:
        Dict with 'success', 'memory'/'error'
    """
    try:
        memory = _set_memory(key, value, description)
        return {"success": True, "memory": memory, "message": "Memory updated successfully"}
    except Exception as e:
        return {"success": False, "error": f"Error setting memory: {e!s}"}


async def list_memories() -> dict:
    """
    List all pinned memory entries.

    Returns:
        Dict with 'success', 'memories'/'error'
    """
    try:
        memories = [_get_memory(k) for k in _pinned]
        return {"success": True, "memories": memories, "count": len(memories)}
    except Exception as e:
        return {"success": False, "error": f"Error listing memories: {e!s}"}


async def delete_memory(key: str) -> dict:
    """
    Delete a pinned memory entry.

    Args:
        key: The memory key to delete

    Returns:
        Dict with 'success', 'message'/'error'
    """
    try:
        if _get_memory(key) is None:
            return {"success": False, "error": f"Memory with key '{key}' not found"}
        _delete_memory(key)
        return {"success": True, "message": f"Memory with key '{key}' deleted successfully"}
    except Exception as e:
        return {"success": False, "error": f"Error deleting memory: {e!s}"}


def register_tools(registry: ToolRegistry):
    """Register memory management tools with the registry."""
    
    # Get memory tool
    get_tool = ToolDefinition(
        name="memory_get",
        description="Retrieve a pinned memory entry by key. Use this to access persistent context that spans conversations.",
        parameters={
            "type": "object",
            "properties": {
                "key": {
                    "type": "string",
                    "description": "The memory key to retrieve"
                }
            },
            "required": ["key"]
        },
        executor=get_memory,
        metadata={
            "category": "memory",
            "audit_level": "summary"
        }
    )
    
    # Set memory tool
    set_tool = ToolDefinition(
        name="memory_set",
        description="Create or update a pinned memory entry. Use this to persist important context like user preferences, project details, or recurring facts.",
        parameters={
            "type": "object",
            "properties": {
                "key": {
                    "type": "string",
                    "description": "The memory key (use descriptive, snake_case names like 'user_timezone' or 'project_name')"
                },
                "value": {
                    "type": "string",
                    "description": "The memory value to store"
                },
                "description": {
                    "type": "string",
                    "description": "Optional description of what this memory represents"
                }
            },
            "required": ["key", "value"]
        },
        executor=set_memory,
        metadata={
            "category": "memory",
            "audit_level": "full"
        }
    )
    
    # List memories tool
    list_tool = ToolDefinition(
        name="memory_list",
        description="List all pinned memory entries. Use this to see what persistent context is available.",
        parameters={
            "type": "object",
            "properties": {}
        },
        executor=list_memories,
        metadata={
            "category": "memory",
            "audit_level": "summary"
        }
    )
    
    # Delete memory tool
    delete_tool = ToolDefinition(
        name="memory_delete",
        description="Delete a pinned memory entry. Use this to remove outdated or no-longer-needed context.",
        parameters={
            "type": "object",
            "properties": {
                "key": {
                    "type": "string",
                    "description": "The memory key to delete"
                }
            },
            "required": ["key"]
        },
        executor=delete_memory,
        metadata={
            "category": "memory",
            "audit_level": "full"
        }
    )
    
    registry.register(get_tool)
    registry.register(set_tool)
    registry.register(list_tool)
    registry.register(delete_tool)
